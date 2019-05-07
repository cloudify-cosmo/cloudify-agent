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

import time
import os

from mock import patch
from testtools import TestCase

from cloudify_agent.api.pm.detach import DetachedDaemon

from cloudify_agent.tests.api.pm import BaseDaemonProcessManagementTest
from cloudify_agent.tests.api.pm import only_os
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.internal.get_storage_directory',
       get_storage_directory)
@only_os('posix')
class TestDetachedDaemon(BaseDaemonProcessManagementTest, TestCase):

    @property
    def daemon_cls(self):
        return DetachedDaemon

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
        self.assertFalse(os.path.exists(daemon.pid_file))

    def test_cron_respawn(self):
        daemon = self.create_daemon(cron_respawn=True, cron_respawn_delay=1)
        daemon.create()
        daemon.configure()
        daemon.start()

        # sleeps so the cron won't respawn the agent before we make sure
        # it's dead
        time.sleep(5)

        # check it started
        timeout = daemon.cron_respawn_delay * 60 + 20
        self.wait_for_daemon_alive(daemon.queue, timeout=timeout)

        # lets kill the process
        self.runner.run("pkill -9 -f 'cloudify_agent.worker'")
        self.wait_for_daemon_dead(daemon.queue)

        # check it was respawned
        timeout = daemon.cron_respawn_delay * 60 + 20
        self.wait_for_daemon_alive(daemon.queue, timeout=timeout)

        # this should also disable the crontab entry
        daemon.stop()
        self.wait_for_daemon_dead(daemon.queue, timeout=timeout)

        # sleep the cron delay time and make sure the daemon is still dead
        time.sleep(daemon.cron_respawn_delay * 60 + 20)
        self.assert_daemon_dead(daemon.queue)
