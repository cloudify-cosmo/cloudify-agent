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
from mock import patch

from cloudify_agent.api.pm.initd import GenericLinuxDaemon

from cloudify_agent.tests.api.pm import BaseDaemonProcessManagementTest
from cloudify_agent.tests.api.pm import patch_unless_ci
from cloudify_agent.tests.api.pm import only_ci
from cloudify_agent.tests.api.pm import only_os
from cloudify_agent.tests import get_storage_directory


def _non_service_start_command(daemon):
    return 'sudo {0} start'.format(daemon.script_path)


def _non_service_stop_command(daemon):
    return 'sudo {0} stop'.format(daemon.script_path)


def _non_service_status_command(daemon):
    return 'sudo {0} status'.format(daemon.script_path)


SCRIPT_DIR = '/tmp/etc/init.d'
CONFIG_DIR = '/tmp/etc/default'


@patch('cloudify_agent.api.utils.internal.get_storage_directory',
       get_storage_directory)
@patch_unless_ci(
    'cloudify_agent.api.pm.initd.GenericLinuxDaemon.SCRIPT_DIR',
    SCRIPT_DIR)
@patch_unless_ci(
    'cloudify_agent.api.pm.initd.GenericLinuxDaemon.CONFIG_DIR',
    CONFIG_DIR)
@patch_unless_ci(
    'cloudify_agent.api.pm.initd.status_command',
    _non_service_status_command)
@patch_unless_ci(
    'cloudify_agent.api.pm.initd.start_command',
    _non_service_start_command)
@patch_unless_ci(
    'cloudify_agent.api.pm.initd.stop_command',
    _non_service_stop_command)
@nose.tools.istest
@only_os('posix')
class TestGenericLinuxDaemon(BaseDaemonProcessManagementTest):

    @property
    def daemon_cls(self):
        return GenericLinuxDaemon

    def test_configure(self):
        daemon = self.create_daemon()
        daemon.create()

        daemon.configure()
        self.assertTrue(os.path.exists(daemon.script_path))
        self.assertTrue(os.path.exists(daemon.config_path))

    def test_delete(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.stop()
        daemon.delete()
        self.assertFalse(os.path.exists(daemon.script_path))
        self.assertFalse(os.path.exists(daemon.config_path))

    @only_ci
    def test_configure_start_on_boot(self):
        daemon = self.create_daemon(start_on_boot=True)
        daemon.create()
        daemon.configure()

    def test_cron_respawn(self):
        daemon = self.create_daemon(cron_respawn=True, respawn_delay=1)
        daemon.create()
        daemon.configure()
        daemon.start()

        # lets kill the process
        self.runner.run("pkill -9 -f 'celery'")
        self.wait_for_daemon_dead(daemon.name)

        # check it was respawned
        timeout = daemon.cron_respawn_delay * 60 + 10
        self.wait_for_daemon_alive(daemon.name, timeout=timeout)

        # this should also disable the crontab entry
        daemon.stop()
        self.wait_for_daemon_dead(daemon.name)

        # sleep the cron delay time and make sure the daemon is still dead
        time.sleep(daemon.cron_respawn_delay * 60 + 5)
        self.assert_daemon_dead(daemon.name)
