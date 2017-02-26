#########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

import os
import nose.tools
import time
import inspect
import types
from functools import wraps
from mock import _get_target
from mock import patch

from celery import Celery

from cloudify import constants
from cloudify.utils import LocalCommandRunner

from cloudify_agent.api import utils, defaults
from cloudify_agent.api import exceptions
from cloudify_agent.api.plugins.installer import PluginInstaller

from cloudify_agent.tests import resources
from cloudify_agent.tests import utils as test_utils
from cloudify_agent.tests import BaseTest, agent_ssl_cert


BUILT_IN_TASKS = [
    'cloudify.dispatch.dispatch',
    'cluster-update'
]
PLUGIN_NAME = 'plugin'
DEPLOYMENT_ID = 'deployment'


def ci():
    return True
    for env_var in ['TRAVIS_BUILD_DIR', 'APPVEYOR', 'CIRCLE_BUILD_NUM']:
        if env_var in os.environ:
            return True
    return False


def patch_unless_ci(target, new):

    if not ci():
        return patch(target, new)
    else:
        getter, attribute = _get_target(target)
        return patch(target, getattr(getter(), attribute))


def only_ci(func):

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not ci():
            raise RuntimeError('Error! This test cannot be executed '
                               'outside of the travis or circle CI '
                               'system since it may corrupt '
                               'your local system files')
        func(*args, **kwargs)

    return wrapper


def only_os(os_type):

    def decorator(test):

        if isinstance(test, (types.MethodType, types.FunctionType)):
            if os.name != os_type:
                return lambda: None
            else:
                return test

        if isinstance(test, type):
            for name, fn in inspect.getmembers(test):
                if isinstance(fn, types.UnboundMethodType):
                    if name.startswith('test') or name.endswith('test'):
                        setattr(test, name, decorator(fn))
            return test

        raise ValueError("'test' argument is of an unsupported type: {0}. "
                         "supported types are: 'type', 'FunctionType',"
                         " 'MethodType'".format(type(test)))
    return decorator


class BaseDaemonLiveTestCase(BaseTest):

    def setUp(self):
        super(BaseDaemonLiveTestCase, self).setUp()
        self.celery = Celery(broker='amqp://',
                             backend='amqp://')
        self.celery.conf.update(
            CELERY_TASK_RESULT_EXPIRES=defaults.CELERY_TASK_RESULT_EXPIRES)
        self.runner = LocalCommandRunner(logger=self.logger)
        self.daemons = []

    def tearDown(self):
        super(BaseDaemonLiveTestCase, self).tearDown()
        if self.celery:
            self.celery.close()
        if os.name == 'nt':
            # with windows we need to stop and remove the service
            nssm_path = utils.get_absolute_resource_path(
                os.path.join('pm', 'nssm', 'nssm.exe'))
            for daemon in self.daemons:
                self.runner.run('sc stop {0}'.format(daemon.name),
                                exit_on_failure=False)
                self.runner.run('{0} remove {1} confirm'
                                .format(nssm_path, daemon.name),
                                exit_on_failure=False)
        else:
            self.runner.run("pkill -9 -f 'celery'", exit_on_failure=False)

    def assert_registered_tasks(self, name):
        destination = 'celery@{0}'.format(name)
        c_inspect = self.celery.control.inspect(destination=[destination])
        registered = c_inspect.registered() or {}
        daemon_tasks = set(t for t in registered[destination]
                           if 'celery' not in t)
        self.assertEqual(set(BUILT_IN_TASKS), daemon_tasks)

    def assert_daemon_alive(self, name):
        registered = utils.get_agent_registered(name, self.celery)
        self.assertTrue(registered is not None)

    def assert_daemon_dead(self, name):
        registered = utils.get_agent_registered(name, self.celery)
        self.assertTrue(registered is None)

    def wait_for_daemon_alive(self, name, timeout=10):
        deadline = time.time() + timeout

        while time.time() < deadline:
            registered = utils.get_agent_registered(name, self.celery)
            if registered:
                return
            self.logger.info('Waiting for daemon {0} to start...'
                             .format(name))
            time.sleep(5)
        raise RuntimeError('Failed waiting for daemon {0} to start. Waited '
                           'for {1} seconds'.format(name, timeout))

    def wait_for_daemon_dead(self, name, timeout=10):
        deadline = time.time() + timeout

        while time.time() < deadline:
            registered = utils.get_agent_registered(name, self.celery)
            if not registered:
                return
            self.logger.info('Waiting for daemon {0} to stop...'
                             .format(name))
            time.sleep(1)
        raise RuntimeError('Failed waiting for daemon {0} to stop. Waited '
                           'for {1} seconds'.format(name, timeout))

    def get_agent_dict(self, env, name='host'):
        node_instances = env.storage.get_node_instances()
        agent_host = [n for n in node_instances if n['name'] == name][0]
        return agent_host['runtime_properties']['cloudify_agent']


def patch_get_source(fn):
    return patch('cloudify_agent.api.plugins.installer.get_plugin_source',
                 lambda plugin, blueprint_id: plugin.get('source'))(fn)


@nose.tools.nottest
class BaseDaemonProcessManagementTest(BaseDaemonLiveTestCase):

    def setUp(self):
        super(BaseDaemonProcessManagementTest, self).setUp()
        self.installer = PluginInstaller(logger=self.logger)

    def tearDown(self):
        super(BaseDaemonProcessManagementTest, self).tearDown()
        self.installer.uninstall(plugin=self.plugin_struct())
        self.installer.uninstall(plugin=self.plugin_struct(),
                                 deployment_id=DEPLOYMENT_ID)

    @property
    def daemon_cls(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def create_daemon(self, **attributes):
        name = utils.internal.generate_agent_name()
        local_rest_cert_file = agent_ssl_cert.get_local_cert_path()

        params = {
            'rest_host': '127.0.0.1',
            'broker_ip': '127.0.0.1',
            'file_server_host': '127.0.0.1',
            'user': self.username,
            'workdir': self.temp_folder,
            'logger': self.logger,
            'name': name,
            'queue': '{0}-queue'.format(name),
            'local_rest_cert_file': local_rest_cert_file
        }
        params.update(attributes)

        daemon = self.daemon_cls(**params)
        self.daemons.append(daemon)
        return daemon

    def test_create(self):
        daemon = self.create_daemon()
        daemon.create()

    def test_configure(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def test_start(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        self.assert_daemon_alive(daemon.name)
        self.assert_registered_tasks(daemon.name)

    def test_start_delete_amqp_queue(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()

        # this creates the queue
        daemon.start()

        daemon.stop()
        daemon.start(delete_amqp_queue=True)

    @patch_get_source
    def test_start_with_error(self):
        log_file = 'H:\\WATT\\lo' if os.name == 'nt' else '/root/no_permission'
        daemon = self.create_daemon(log_file=log_file)
        daemon.create()
        daemon.configure()
        try:
            daemon.start()
            self.fail('Expected start operation to fail due to bad logfile')
        except exceptions.DaemonError as e:
            if os.name == 'nt':
                expected_error = "No such file or directory: '"
            else:
                expected_error = "Permission denied: '{0}"
            self.assertIn(expected_error.format(log_file), str(e))

    def test_start_short_timeout(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        try:
            daemon.start(timeout=-1)
        except exceptions.DaemonStartupTimeout as e:
            self.assertTrue('failed to start in -1 seconds' in str(e))

    def test_status(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.assertFalse(daemon.status())
        daemon.start()
        self.assertTrue(daemon.status())

    def test_stop(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.stop()
        self.assert_daemon_dead(daemon.name)

    def test_stop_short_timeout(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        try:
            daemon.stop(timeout=-1)
        except exceptions.DaemonShutdownTimeout as e:
            self.assertTrue('failed to stop in -1 seconds' in str(e))

    @patch_get_source
    def test_restart(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.installer.install(self.plugin_struct())
        daemon.start()
        daemon.restart()
        self.assert_daemon_alive(daemon.name)
        self.assert_registered_tasks(daemon.name)

    def test_two_daemons(self):
        daemon1 = self.create_daemon()
        daemon1.create()
        daemon1.configure()

        daemon1.start()
        self.assert_daemon_alive(daemon1.name)
        self.assert_registered_tasks(daemon1.name)

        daemon2 = self.create_daemon()
        daemon2.create()
        daemon2.configure()

        daemon2.start()
        self.assert_daemon_alive(daemon2.name)
        self.assert_registered_tasks(daemon2.name)

    @patch_get_source
    def test_conf_env_variables(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.installer.install(self.plugin_struct())
        daemon.start()

        expected = {
            constants.REST_HOST_KEY: str(daemon.rest_host),
            constants.REST_PORT_KEY: str(daemon.rest_port),
            constants.FILE_SERVER_HOST_KEY: str(daemon.file_server_host),
            constants.FILE_SERVER_PORT_KEY: str(daemon.file_server_port),
            constants.FILE_SERVER_PROTOCOL_KEY:
                str(daemon.file_server_protocol),
            constants.MANAGER_FILE_SERVER_URL_KEY:
                '{0}://{1}:{2}'.format(daemon.file_server_protocol,
                                       daemon.file_server_host,
                                       daemon.file_server_port),
            constants.MANAGER_FILE_SERVER_BLUEPRINTS_ROOT_URL_KEY:
                '{0}://{1}:{2}/blueprints'.format(daemon.file_server_protocol,
                                                  daemon.file_server_host,
                                                  daemon.file_server_port),
            constants.MANAGER_FILE_SERVER_DEPLOYMENTS_ROOT_URL_KEY:
                '{0}://{1}:{2}/deployments'.format(daemon.file_server_protocol,
                                                   daemon.file_server_host,
                                                   daemon.file_server_port),
            constants.CELERY_WORK_DIR_KEY: daemon.workdir,
            utils.internal.CLOUDIFY_DAEMON_STORAGE_DIRECTORY_KEY:
                utils.internal.get_storage_directory(),
            utils.internal.CLOUDIFY_DAEMON_NAME_KEY: daemon.name,
            utils.internal.CLOUDIFY_DAEMON_USER_KEY: daemon.user
        }

        def _get_env_var(var):
            return self.send_task(
                task_name='mock_plugin.tasks.get_env_variable',
                queue=daemon.queue,
                kwargs={'env_variable': var})

        def _check_env_var(var, expected_value):
            _value = _get_env_var(var)
            self.assertEqual(_value, expected_value)

        for key, value in expected.iteritems():
            _check_env_var(key, value)

    @patch_get_source
    def test_extra_env(self):
        daemon = self.create_daemon()
        daemon.extra_env_path = utils.env_to_file(
            {'TEST_ENV_KEY': 'TEST_ENV_VALUE'},
            posix=os.name == 'posix'
        )
        daemon.create()
        daemon.configure()
        self.installer.install(self.plugin_struct())
        daemon.start()

        # check the env file was properly sourced by querying the env
        # variable from the daemon process. this is done by a task
        value = self.send_task(
            task_name='mock_plugin.tasks.get_env_variable',
            queue=daemon.queue,
            kwargs={'env_variable': 'TEST_ENV_KEY'})
        self.assertEqual(value, 'TEST_ENV_VALUE')

    @patch_get_source
    def test_execution_env(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.installer.install(self.plugin_struct())
        daemon.start()

        # check that cloudify.dispatch.dispatch 'execution_env' processing
        # works.
        # not the most ideal place for this test. but on the other hand
        # all the boilerplate is already here, so this is too tempting.
        value = self.send_task(
            task_name='mock_plugin.tasks.get_env_variable',
            queue=daemon.queue,
            kwargs={'env_variable': 'TEST_ENV_KEY2'},
            execution_env={'TEST_ENV_KEY2': 'TEST_ENV_VALUE2'})
        self.assertEqual(value, 'TEST_ENV_VALUE2')

    def test_delete(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def test_delete_before_stop(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        self.assertRaises(exceptions.DaemonStillRunningException,
                          daemon.delete)

    def test_delete_before_stop_with_force(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.delete(force=True)
        self.assert_daemon_dead(daemon.name)

    @patch_get_source
    def test_logging(self):
        message = 'THIS IS THE TEST MESSAGE LOG CONTENT'

        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.installer.install(self.plugin_struct())
        self.installer.install(self.plugin_struct(),
                               deployment_id=DEPLOYMENT_ID)
        daemon.start()

        def log_and_assert(_message, _deployment_id=None):
            self.send_task(
                task_name='mock_plugin.tasks.do_logging',
                queue=daemon.queue,
                kwargs={'message': _message},
                deployment_id=_deployment_id)

            name = _deployment_id if _deployment_id else '__system__'
            logdir = os.path.join(daemon.workdir, 'logs')
            logfile = os.path.join(logdir, '{0}.log'.format(name))
            try:
                with open(logfile) as f:
                    self.assertIn(_message, f.read())
            except IOError:
                self.logger.warning('{0} content: {1}'
                                    .format(logdir, os.listdir(logdir)))
                raise

        # Test __system__ logs
        log_and_assert(message)
        # Test deployment logs
        log_and_assert(message, DEPLOYMENT_ID)

    @staticmethod
    def plugin_struct(plugin_name='mock-plugin'):
        return {
            'source': os.path.join(resources.get_resource('plugins'),
                                   plugin_name),
            'name': PLUGIN_NAME
        }

    def send_task(self,
                  task_name,
                  queue,
                  deployment_id=None,
                  args=None,
                  kwargs=None,
                  timeout=10,
                  execution_env=None):
        cloudify_context = test_utils.op_context(task_name,
                                                 task_target=queue,
                                                 plugin_name=PLUGIN_NAME,
                                                 execution_env=execution_env,
                                                 deployment_id=deployment_id)
        kwargs = kwargs or {}
        kwargs['__cloudify_context'] = cloudify_context
        return self.celery.send_task(
            name='cloudify.dispatch.dispatch',
            queue=queue,
            args=args,
            kwargs=kwargs).get(timeout=timeout)
