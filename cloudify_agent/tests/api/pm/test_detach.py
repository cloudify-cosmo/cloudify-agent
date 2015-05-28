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

import time
from mock import patch

from cloudify_agent.api.pm.detach import DetachedDaemon

from cloudify_agent.tests.api.pm import BaseDaemonLiveTestCase
from cloudify_agent.tests.api.pm import only_os
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.get_storage_directory',
       get_storage_directory)
@patch('cloudify_agent.api.pm.base.get_storage_directory',
       get_storage_directory)
@only_os('posix')
class TestDetachedDaemon(BaseDaemonLiveTestCase):

    def create_daemon(self, name=None, queue=None, **attributes):

        if name is None:
            name = self.name
        if queue is None:
            queue = self.queue

        return DetachedDaemon(
            name=name,
            queue=queue,
            manager_ip='127.0.0.1',
            user=self.username,
            workdir=self.temp_folder,
            logger=self.logger,
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

    def test_status(self):
        self._test_status_impl()

    def test_start_delete_amqp_queue(self):
        self._test_start_delete_amqp_queue_impl()

    def test_start_with_error(self):
        self._test_start_with_error_impl()

    def test_start_short_timeout(self):
        self._test_start_short_timeout_impl()

    def test_two_daemons(self):
        self._test_two_daemons_impl()

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
