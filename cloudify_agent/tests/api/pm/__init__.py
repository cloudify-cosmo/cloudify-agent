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

from cloudify_agent import VIRTUALENV
from cloudify_agent.api import utils, defaults
from cloudify_agent.api import exceptions
from cloudify_agent.api.plugins.installer import PluginInstaller

from cloudify_agent.tests import BaseTest
from cloudify_agent.tests import resources


BUILT_IN_TASKS = [
    'cloudify.plugins.workflows.scale',
    'cloudify.plugins.workflows.auto_heal_reinstall_node_subgraph',
    'cloudify.plugins.workflows.uninstall',
    'cloudify.plugins.workflows.execute_operation',
    'cloudify.plugins.workflows.install',
    'script_runner.tasks.execute_workflow',
    'script_runner.tasks.run',
    'diamond_agent.tasks.install',
    'diamond_agent.tasks.uninstall',
    'diamond_agent.tasks.start',
    'diamond_agent.tasks.stop',
    'diamond_agent.tasks.add_collectors',
    'diamond_agent.tasks.del_collectors',
    'cloudify_agent.operations.install_plugins',
    'cloudify_agent.operations.restart',
    'cloudify_agent.operations.stop',
    'cloudify_agent.installer.operations.create',
    'cloudify_agent.installer.operations.configure',
    'cloudify_agent.installer.operations.start',
    'cloudify_agent.installer.operations.stop',
    'cloudify_agent.installer.operations.delete',
    'cloudify_agent.installer.operations.restart',
    'worker_installer.tasks.install',
    'worker_installer.tasks.start',
    'worker_installer.tasks.stop',
    'worker_installer.tasks.restart',
    'worker_installer.tasks.uninstall',
    'windows_agent_installer.tasks.install',
    'windows_agent_installer.tasks.start',
    'windows_agent_installer.tasks.stop',
    'windows_agent_installer.tasks.restart',
    'windows_agent_installer.tasks.uninstall',
    'plugin_installer.tasks.install',
    'windows_plugin_installer.tasks.install'
]


def ci():
    return 'TRAVIS_BUILD_DIR' in os.environ or 'APPVEYOR' in os.environ


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
                               'outside of the travis CI '
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

    def assert_registered_tasks(self, name, additional_tasks=None):
        if not additional_tasks:
            additional_tasks = set()
        destination = 'celery@{0}'.format(name)
        c_inspect = self.celery.control.inspect(destination=[destination])
        registered = c_inspect.registered() or {}

        def include(task):
            return 'celery' not in task

        daemon_tasks = set(filter(include, set(registered[destination])))
        expected_tasks = set(BUILT_IN_TASKS)
        expected_tasks.update(additional_tasks)
        self.assertEqual(expected_tasks, daemon_tasks)

    def assert_daemon_alive(self, name):
        stats = utils.get_agent_stats(name, self.celery)
        self.assertTrue(stats is not None)

    def assert_daemon_dead(self, name):
        stats = utils.get_agent_stats(name, self.celery)
        self.assertTrue(stats is None)

    def wait_for_daemon_alive(self, name, timeout=10):
        deadline = time.time() + timeout

        while time.time() < deadline:
            stats = utils.get_agent_stats(name, self.celery)
            if stats:
                return
            self.logger.info('Waiting for daemon {0} to start...'
                             .format(name))
            time.sleep(5)
        raise RuntimeError('Failed waiting for daemon {0} to start. Waited '
                           'for {1} seconds'.format(name, timeout))

    def wait_for_daemon_dead(self, name, timeout=10):
        deadline = time.time() + timeout

        while time.time() < deadline:
            stats = utils.get_agent_stats(name, self.celery)
            if not stats:
                return
            self.logger.info('Waiting for daemon {0} to stop...'
                             .format(name))
            time.sleep(1)
        raise RuntimeError('Failed waiting for daemon {0} to stop. Waited '
                           'for {1} seconds'.format(name, timeout))


@nose.tools.nottest
class BaseDaemonProcessManagementTest(BaseDaemonLiveTestCase):

    def setUp(self):
        super(BaseDaemonProcessManagementTest, self).setUp()
        self.installer = PluginInstaller(logger=self.logger)

    def tearDown(self):
        super(BaseDaemonProcessManagementTest, self).tearDown()
        self.installer.uninstall('mock-plugin')
        self.installer.uninstall('mock-plugin-error')

    @property
    def daemon_cls(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def create_daemon(self, **attributes):

        name = utils.internal.generate_agent_name()

        params = {
            'manager_ip': '127.0.0.1',
            'user': self.username,
            'workdir': self.temp_folder,
            'logger': self.logger,
            'name': name,
            'queue': '{0}-queue'.format(name)
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

    def test_start_with_error(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.installer.install(
            os.path.join(resources.get_resource('plugins'),
                         'mock-plugin-error'))
        daemon.register('mock-plugin-error')
        try:
            daemon.start()
            self.fail('Expected start operation to fail '
                      'due to bad import')
        except exceptions.DaemonError as e:
            self.assertIn('cannot import name non_existent', str(e))

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

    def test_register(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.installer.install(
            os.path.join(resources.get_resource('plugins'),
                         'mock-plugin'))
        daemon.register('mock-plugin')
        daemon.start()
        self.assert_registered_tasks(
            daemon.name,
            additional_tasks=set(['mock_plugin.tasks.run',
                                  'mock_plugin.tasks.get_env_variable'])
        )

    def test_unregister(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.installer.install(
            os.path.join(resources.get_resource('plugins'),
                         'mock-plugin'))
        daemon.register('mock-plugin')
        daemon.start()
        self.assert_registered_tasks(
            daemon.name,
            additional_tasks=set(['mock_plugin.tasks.run',
                                  'mock_plugin.tasks.get_env_variable'])
        )
        daemon.unregister('mock-plugin')
        daemon.restart()
        self.assert_registered_tasks(daemon.name)

    def test_restart(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.installer.install(
            os.path.join(resources.get_resource('plugins'),
                         'mock-plugin'))
        daemon.start()
        daemon.register('mock-plugin')
        daemon.restart()
        self.assert_registered_tasks(
            daemon.name,
            additional_tasks=set(['mock_plugin.tasks.run',
                                  'mock_plugin.tasks.get_env_variable'])
        )

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

    def test_conf_env_variables(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.installer.install(
            os.path.join(resources.get_resource('plugins'),
                         'mock-plugin'))
        daemon.register('mock-plugin')
        daemon.start()

        expected = {
            constants.MANAGER_IP_KEY: str(daemon.manager_ip),
            constants.MANAGER_REST_PORT_KEY: str(daemon.manager_port),
            constants.MANAGER_FILE_SERVER_URL_KEY:
                'http://{0}:53229'.format(daemon.manager_ip),
            constants.MANAGER_FILE_SERVER_BLUEPRINTS_ROOT_URL_KEY:
                'http://{0}:53229/blueprints'.format(daemon.manager_ip),
            constants.CELERY_BROKER_URL_KEY: daemon.broker_url,
            utils.internal.CLOUDIFY_DAEMON_STORAGE_DIRECTORY_KEY:
                utils.internal.get_storage_directory(),
            utils.internal.CLOUDIFY_DAEMON_NAME_KEY: daemon.name,
            utils.internal.CLOUDIFY_DAEMON_USER_KEY: daemon.user
        }

        def _get_env_var(var):
            return self.celery.send_task(
                name='mock_plugin.tasks.get_env_variable',
                queue=daemon.queue,
                args=[var]).get(timeout=5)

        def _check_env_var(var, expected_value):
            _value = _get_env_var(var)
            self.assertEqual(_value, expected_value)

        for key, value in expected.iteritems():
            _check_env_var(key, value)

        def _check_env_path():
            _path = _get_env_var('PATH')
            self.assertIn(VIRTUALENV, _path)
        _check_env_path()

    def test_extra_env_path(self):
        daemon = self.create_daemon()
        daemon.extra_env_path = utils.env_to_file(
            {'TEST_ENV_KEY': 'TEST_ENV_VALUE'},
            posix=os.name == 'posix'
        )
        daemon.create()
        daemon.configure()
        self.installer.install(
            os.path.join(resources.get_resource('plugins'),
                         'mock-plugin'))
        daemon.register('mock-plugin')
        daemon.start()

        # check the env file was properly sourced by querying the env
        # variable from the daemon process. this is done by a task
        value = self.celery.send_task(
            name='mock_plugin.tasks.get_env_variable',
            queue=daemon.queue,
            args=['TEST_ENV_KEY']).get(timeout=10)
        self.assertEqual(value, 'TEST_ENV_VALUE')

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
