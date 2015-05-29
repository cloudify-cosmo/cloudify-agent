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
import time
import inspect
import types
import getpass
import logging
import tempfile
import shutil
from functools import wraps
from mock import _get_target
from mock import patch

from celery import Celery

from cloudify import constants
from cloudify.utils import LocalCommandRunner
from cloudify.utils import setup_logger


from cloudify_agent.api import utils
from cloudify_agent.api import exceptions
from cloudify_agent.api import errors

from cloudify_agent.tests import BaseTest
from cloudify_agent.tests import resources
from cloudify_agent.tests import utils as test_utils


BUILT_IN_TASKS = [
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
    'cloudify_agent.installer.operations.restart'
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
        self.logger = setup_logger(
            'cloudify-agent.tests.api.pm',
            logger_level=logging.DEBUG)

        utils.logger.setLevel(logging.DEBUG)

        self.name = utils.generate_agent_name()
        self.queue = '{0}-queue'.format(self.name)
        self.additional_names = []

        self.runner = LocalCommandRunner(self.logger)
        self.temp_folder = tempfile.mkdtemp(prefix='cfy-agent-tests-')
        self.currdir = os.getcwd()
        self.username = getpass.getuser()
        self.logger.info('Working directory: {0}'.format(self.temp_folder))
        os.chdir(self.temp_folder)

    def tearDown(self):
        super(BaseDaemonLiveTestCase, self).tearDown()
        os.chdir(self.currdir)
        if os.name == 'nt':
            # with windows we need to stop and remove the service
            names = self.additional_names
            names.append(self.name)
            for name in names:
                nssm_path = utils.get_absolute_resource_path(
                    os.path.join('pm', 'nssm', 'nssm.exe'))
                self.runner.run('sc stop {0}'.format(name),
                                exit_on_failure=False,
                                stderr_pipe=False,
                                stdout_pipe=False)
                self.runner.run('{0} remove {1} confirm'
                                .format(nssm_path, name),
                                exit_on_failure=False,
                                stderr_pipe=False,
                                stdout_pipe=False)
        else:
            self.runner.run("pkill -9 -f 'celery'", exit_on_failure=False)

    def create_daemon(self, name=None, queue=None, **attributes):
        raise NotImplementedError('Must be implemented by sub-class')

    ##############################################################
    # generic tests relevant to all process management types
    ##############################################################

    def _test_create_impl(self):
        daemon = self.create_daemon()
        daemon.create()

    def _test_configure_existing_agent_impl(self):
        daemon = self.create_daemon()
        daemon.create()

        daemon.configure()
        self.assertRaises(errors.DaemonError, daemon.configure)

    def _test_start_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        self.assert_daemon_alive(daemon.name)
        self.assert_registered_tasks(daemon.name)

    def _test_start_delete_amqp_queue_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()

        # this creates the queue
        daemon.start()

        daemon.stop()
        daemon.start(delete_amqp_queue=True)

    def _test_start_with_error_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        test_utils.install_package(os.path.join(
            resources.get_resource('plugins'), 'mock-plugin-error'
        ))
        try:
            daemon.register('mock-plugin-error')
            try:
                daemon.start()
                self.fail('Expected start operation to fail '
                          'due to bad import')
            except errors.DaemonError as e:
                self.assertIn('cannot import name non_existent', str(e))
        finally:
            test_utils.uninstall_package_if_exists('mock-plugin-error')

    def _test_start_short_timeout_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        try:
            daemon.start(timeout=-1)
        except exceptions.DaemonStartupTimeout as e:
            self.assertTrue('failed to start in -1 seconds' in str(e))

    def _test_status_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.assertFalse(daemon.status())
        daemon.start()
        self.assertTrue(daemon.status())

    def _test_stop_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.stop()
        self.assert_daemon_dead(daemon.name)

    def _test_stop_short_timeout_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        try:
            daemon.stop(timeout=-1)
        except exceptions.DaemonShutdownTimeout as e:
            self.assertTrue('failed to stop in -1 seconds' in str(e))

    def _test_register_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        test_utils.install_package(os.path.join(
            resources.get_resource('plugins'), 'mock-plugin'
        ))
        try:
            daemon.register('mock-plugin')
            daemon.start()
            self.assert_registered_tasks(
                daemon.name,
                additional_tasks=set(['mock_plugin.tasks.run',
                                      'mock_plugin.tasks.get_env_variable'])
            )
        finally:
            test_utils.uninstall_package_if_exists('mock-plugin')

    def _test_restart_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        test_utils.install_package(os.path.join(
            resources.get_resource('plugins'), 'mock-plugin'
        ))
        daemon.start()
        try:
            daemon.register('mock-plugin')
            daemon.restart()
            self.assert_registered_tasks(
                daemon.name,
                additional_tasks=set(['mock_plugin.tasks.run',
                                      'mock_plugin.tasks.get_env_variable'])
            )
        finally:
            test_utils.uninstall_package_if_exists('mock-plugin')

    def _test_two_daemons_impl(self):
        queue1 = '{0}-1'.format(self.queue)
        name1 = '{0}-1'.format(self.name)
        daemon1 = self.create_daemon(name=name1, queue=queue1)
        daemon1.create()
        daemon1.configure()

        daemon1.start()
        self.assert_daemon_alive(daemon1.name)
        self.assert_registered_tasks(daemon1.name)

        queue2 = '{0}-2'.format(self.queue)
        name2 = '{0}-2'.format(self.name)
        daemon2 = self.create_daemon(name=name2, queue=queue2)
        daemon2.create()
        daemon2.configure()

        daemon2.start()
        self.assert_daemon_alive(daemon2.name)
        self.assert_registered_tasks(daemon2.name)

    def _test_conf_env_variables_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        test_utils.install_package(os.path.join(
            resources.get_resource('plugins'), 'mock-plugin'
        ))
        try:
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
                constants.CLOUDIFY_DAEMON_STORAGE_DIRECTORY_KEY:
                    utils.get_storage_directory(),
                constants.CLOUDIFY_DAEMON_NAME_KEY: daemon.name,
                constants.CLOUDIFY_DAEMON_USER_KEY: daemon.user
            }

            def _check_env_var(var, expected_value):
                _value = self.celery.send_task(
                    name='mock_plugin.tasks.get_env_variable',
                    queue=self.queue,
                    args=[var]).get(timeout=5)
                self.assertEqual(_value, expected_value)

            for key, value in expected.iteritems():
                _check_env_var(key, value)

        finally:
            test_utils.uninstall_package_if_exists('mock-plugin')

    def _test_extra_env_path_impl(self):
        daemon = self.create_daemon()
        daemon.extra_env_path = utils.env_to_file(
            {'TEST_ENV_KEY': 'TEST_ENV_VALUE'},
            posix=os.name == 'posix'
        )
        daemon.create()
        daemon.configure()
        test_utils.install_package(os.path.join(
            resources.get_resource('plugins'), 'mock-plugin'
        ))
        try:
            daemon.register('mock-plugin')
            daemon.start()

            # check the env file was properly sourced by querying the env
            # variable from the daemon process. this is done by a task
            value = self.celery.send_task(
                name='mock_plugin.tasks.get_env_variable',
                queue=self.queue,
                args=['TEST_ENV_KEY']).get(timeout=10)
            self.assertEqual(value, 'TEST_ENV_VALUE')
        finally:
            test_utils.uninstall_package_if_exists('mock-plugin')

    def _test_delete_before_stop_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        self.assertRaises(exceptions.DaemonStillRunningException,
                          daemon.delete)

    def _test_delete_before_stop_with_force_impl(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.delete(force=True)
        self.assert_daemon_dead(self.name)

    def _smakedirs(self, dirs):
        if not os.path.exists(dirs):
            os.makedirs(dirs)

    def _srmtree(self, tree):
        if os.path.exists(tree):
            shutil.rmtree(tree)

    def assert_registered_tasks(self, name, additional_tasks=None):
        if not additional_tasks:
            additional_tasks = set()
        destination = 'celery@{0}'.format(name)
        cinspect = self.celery.control.inspect(destination=[destination])
        registered = cinspect.registered() or {}

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
