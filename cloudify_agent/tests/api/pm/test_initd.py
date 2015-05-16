#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
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

import uuid
import os
import logging
from mock import patch

from cloudify import constants

from cloudify_agent import VIRTUALENV
from cloudify_agent.api import utils
from cloudify_agent.api import exceptions
from cloudify_agent.api import errors
from cloudify_agent.api.pm.initd import GenericLinuxDaemon

from cloudify_agent.tests import resources
from cloudify_agent.tests.api.pm import BaseDaemonLiveTestCase
from cloudify_agent.tests.api.pm import patch_unless_travis
from cloudify_agent.tests.api.pm import only_travis
from cloudify_agent.tests import get_storage_directory


def _non_service_start_command(daemon):
    return 'sudo {0} start'.format(daemon.script_path)


def _non_service_stop_command(daemon):
    return 'sudo {0} stop'.format(daemon.script_path)


SCRIPT_DIR = '/tmp/etc/init.d'
CONFIG_DIR = '/tmp/etc/default'


@patch('cloudify_agent.api.utils.get_storage_directory',
       get_storage_directory)
@patch_unless_travis(
    'cloudify_agent.api.pm.initd.GenericLinuxDaemon.SCRIPT_DIR',
    SCRIPT_DIR)
@patch_unless_travis(
    'cloudify_agent.api.pm.initd.GenericLinuxDaemon.CONFIG_DIR',
    CONFIG_DIR)
@patch_unless_travis(
    'cloudify_agent.api.pm.initd.start_command',
    _non_service_start_command)
@patch_unless_travis(
    'cloudify_agent.api.pm.initd.stop_command',
    _non_service_stop_command)
class TestGenericLinuxDaemon(BaseDaemonLiveTestCase):

    def setUp(self):
        super(TestGenericLinuxDaemon, self).setUp()
        self.name = 'cloudify-agent-{0}'.format(str(uuid.uuid4())[0:4])
        self.queue = '{0}-queue'.format(self.name)
        self._smakedirs(CONFIG_DIR)
        self._smakedirs(SCRIPT_DIR)

    PROCESS_MANAGEMENT = 'init.d'

    def _create_daemon(self, name=None, queue=None, **attributes):

        if name is None:
            name = self.name
        if queue is None:
            queue = self.queue

        return GenericLinuxDaemon(
            name=name,
            queue=queue,
            manager_ip='127.0.0.1',
            user=self.username,
            workdir=self.temp_folder,
            logger_level=logging.DEBUG,
            **attributes
        )

    def test_create(self):
        daemon = self._create_daemon()
        daemon.create()

    def test_configure(self):
        daemon = self._create_daemon()
        daemon.create()

        daemon.configure()
        self.assertTrue(os.path.exists(daemon.script_path))
        self.assertTrue(os.path.exists(daemon.config_path))
        self.assertTrue(os.path.exists(daemon.includes_path))

    def test_configure_existing_agent(self):
        daemon = self._create_daemon()
        daemon.create()

        daemon.configure()
        self.assertTrue(os.path.exists(daemon.script_path))
        self.assertTrue(os.path.exists(daemon.config_path))
        self.assertTrue(os.path.exists(daemon.includes_path))

        self.assertRaises(errors.DaemonError, daemon.configure)

    @only_travis
    def test_configure_start_on_boot(self):
        daemon = self._create_daemon(start_on_boot=True)
        daemon.create()
        daemon.configure()

    def test_start(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        self.assert_daemon_alive(daemon.name)
        self.assert_registered_tasks(daemon.name)

    def test_start_delete_amqp_queue(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()

        # this creates the queue
        daemon.start()

        daemon.stop()
        daemon.start(delete_amqp_queue=True)

    def test_start_with_error(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()
        self.runner.run('{0}/bin/pip install {1}/mock-plugin-error'
                        .format(VIRTUALENV, resources.get_resource('plugins')),
                        stdout_pipe=False)
        try:
            daemon.register('mock-plugin-error')
            try:
                daemon.start(timeout=5)
                self.fail('Expected start operation to fail '
                          'due to bad import')
            except exceptions.DaemonException as e:
                self.assertIn('cannot import name non_existent', str(e))
        finally:
            self.runner.run('{0}/bin/pip uninstall -y mock-plugin-error'
                            .format(VIRTUALENV),
                            stdout_pipe=False)

    def test_start_short_timeout(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()
        try:
            daemon.start(timeout=-1)
        except exceptions.DaemonStartupTimeout as e:
            self.assertTrue('failed to start in -1 seconds' in str(e))

    def test_stop(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.stop()
        self.assert_daemon_dead(daemon.name)

    def test_stop_short_timeout(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        try:
            daemon.stop(timeout=-1)
        except exceptions.DaemonShutdownTimeout as e:
            self.assertTrue('failed to stop in -1 seconds' in str(e))

    def test_delete(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.stop()
        daemon.delete()
        self.assertFalse(os.path.exists(daemon.script_path))
        self.assertFalse(os.path.exists(daemon.config_path))
        self.assertFalse(os.path.exists(daemon.includes_path))

    def test_delete_before_stop(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        self.assertRaises(exceptions.DaemonStillRunningException,
                          daemon.delete)

    def test_delete_before_stop_with_force(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.delete(force=True)
        self.assert_daemon_dead(self.name)

    def test_register(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()
        self.runner.run('{0}/bin/pip install {1}/mock-plugin'
                        .format(VIRTUALENV, resources.get_resource('plugins')),
                        stdout_pipe=False)
        try:
            daemon.register('mock-plugin')
            daemon.start()
            self.assert_registered_tasks(
                daemon.name,
                additional_tasks=set(['mock_plugin.tasks.run',
                                      'mock_plugin.tasks.get_env_variable'])
            )
        finally:
            self.runner.run('{0}/bin/pip uninstall -y mock-plugin'
                            .format(VIRTUALENV),
                            stdout_pipe=False)

    def test_restart(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()
        from cloudify_agent.tests import resources
        self.runner.run('{0}/bin/pip install {1}/mock-plugin'
                        .format(VIRTUALENV, resources.get_resource('plugins')),
                        stdout_pipe=False)
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
            self.runner.run('{0}/bin/pip uninstall -y mock-plugin'
                            .format(VIRTUALENV),
                            stdout_pipe=False)

    def test_two_daemons(self):
        queue1 = '{0}-1'.format(self.queue)
        name1 = '{0}-1'.format(self.name)
        daemon1 = self._create_daemon(name=name1, queue=queue1)
        daemon1.create()
        daemon1.configure()

        daemon1.start()
        self.assert_daemon_alive(daemon1.name)
        self.assert_registered_tasks(daemon1.name)

        queue2 = '{0}-2'.format(self.queue)
        name2 = '{0}-2'.format(self.name)
        daemon2 = self._create_daemon(name=name2, queue=queue2)
        daemon2.create()
        daemon2.configure()

        daemon2.start()
        self.assert_daemon_alive(daemon2.name)
        self.assert_registered_tasks(daemon2.name)

    def test_conf_env_variables(self):
        daemon = self._create_daemon()
        daemon.create()
        daemon.configure()
        from cloudify_agent.tests import resources
        self.runner.run(
            '{0}/bin/pip install {1}/mock-plugin'
            .format(VIRTUALENV, resources.get_resource('plugins')),
            stdout_pipe=False)
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
                constants.CELERYD_WORK_DIR_KEY: daemon.workdir,
                constants.CELERY_RESULT_BACKEND_KEY: daemon.broker_url,
                constants.CELERY_BROKER_URL_KEY: daemon.broker_url,
                constants.AGENT_PROCESS_MANAGEMENT_KEY: 'init.d',
                constants.AGENT_NAME_KEY: daemon.name
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
            self.runner.run('{0}/bin/pip uninstall -y mock-plugin'
                            .format(VIRTUALENV),
                            stdout_pipe=False)

    def test_extra_env_path(self):
        daemon = self._create_daemon()
        daemon.extra_env_path = utils.env_dict_to_file(
            {'TEST_ENV_KEY': 'TEST_ENV_VALUE'}
        )
        daemon.create()
        daemon.configure()
        from cloudify_agent.tests import resources
        self.runner.run('{0}/bin/pip install {1}/mock-plugin'
                        .format(VIRTUALENV,
                                resources.get_resource('plugins')),
                        stdout_pipe=False)
        try:
            daemon.register('mock-plugin')
            daemon.start()

            # check the env file was properly sourced by querying the env
            # variable from the daemon process. this is done by a task
            value = self.celery.send_task(
                name='mock_plugin.tasks.get_env_variable',
                queue=self.queue,
                args=['TEST_ENV_KEY']).get(timeout=5)
            self.assertEqual(value, 'TEST_ENV_VALUE')
        finally:
            self.runner.run('{0}/bin/pip uninstall -y mock-plugin'
                            .format(VIRTUALENV),
                            stdout_pipe=False)
