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

import os
import logging
from mock import patch

from cloudify_agent.api.pm.initd import GenericLinuxDaemon

from cloudify_agent.tests.api.pm import BaseDaemonLiveTestCase
from cloudify_agent.tests.api.pm import patch_unless_ci
from cloudify_agent.tests.api.pm import only_ci
from cloudify_agent.tests.api.pm import only_os
from cloudify_agent.tests import get_storage_directory


def _non_service_start_command(daemon):
    return 'sudo {0} start'.format(daemon.script_path)


def _non_service_stop_command(daemon):
    return 'sudo {0} stop'.format(daemon.script_path)


SCRIPT_DIR = '/tmp/etc/init.d'
CONFIG_DIR = '/tmp/etc/default'


@patch('cloudify_agent.api.utils.get_storage_directory',
       get_storage_directory)
@patch('cloudify_agent.api.pm.base.get_storage_directory',
       get_storage_directory)
@patch_unless_ci(
    'cloudify_agent.api.pm.initd.GenericLinuxDaemon.SCRIPT_DIR',
    SCRIPT_DIR)
@patch_unless_ci(
    'cloudify_agent.api.pm.initd.GenericLinuxDaemon.CONFIG_DIR',
    CONFIG_DIR)
@patch_unless_ci(
    'cloudify_agent.api.pm.initd.start_command',
    _non_service_start_command)
@patch_unless_ci(
    'cloudify_agent.api.pm.initd.stop_command',
    _non_service_stop_command)
@only_os('posix')
class TestGenericLinuxDaemon(BaseDaemonLiveTestCase):

    def setUp(self):
        super(TestGenericLinuxDaemon, self).setUp()
        self._smakedirs(CONFIG_DIR)
        self._smakedirs(SCRIPT_DIR)

    def create_daemon(self, name=None, queue=None, **attributes):

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

    def test_start(self):
        self._test_start_impl()

    def test_stop(self):
        self._test_stop_impl()

    def test_stop_short_timeout(self):
        self._test_stop_short_timeout_impl()

    def test_register(self):
        self._test_register_impl()

    def test_restart(self):
        self._test_restart_impl()

    def test_create(self):
        self._test_create_impl()

    def test_extra_env_path(self):
        self._test_extra_env_path_impl()

    def test_conf_env_variables(self):
        self._test_conf_env_variables_impl()

    def test_start_delete_amqp_queue(self):
        self._test_start_delete_amqp_queue_impl()

    def test_start_with_error(self):
        self._test_start_with_error_impl()

    def test_start_short_timeout(self):
        self._test_start_short_timeout_impl()

    def test_two_daemons(self):
        self._test_two_daemons_impl()

    def test_configure(self):
        daemon = self.create_daemon()
        daemon.create()

        daemon.configure()
        self.assertTrue(os.path.exists(daemon.script_path))
        self.assertTrue(os.path.exists(daemon.config_path))
        self.assertTrue(os.path.exists(daemon.includes_path))

    def test_configure_existing_agent(self):
        self._test_configure_existing_agent_impl()

    @only_ci
    def test_configure_start_on_boot(self):
        daemon = self.create_daemon(start_on_boot=True)
        daemon.create()
        daemon.configure()

    def test_delete(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.stop()
        daemon.delete()
        self.assertFalse(os.path.exists(daemon.script_path))
        self.assertFalse(os.path.exists(daemon.config_path))
        self.assertFalse(os.path.exists(daemon.includes_path))

    def test_delete_before_stop(self):
        self._test_delete_before_stop_impl()

    def test_delete_before_stop_with_force(self):
        self._test_delete_before_stop_with_force_impl()
