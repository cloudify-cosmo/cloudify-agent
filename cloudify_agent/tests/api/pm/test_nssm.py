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

from mock import patch
from testtools import TestCase

from cloudify.exceptions import CommandExecutionException

from cloudify_agent.api.pm.nssm import NonSuckingServiceManagerDaemon

from cloudify_agent.tests.api.pm import BaseDaemonProcessManagementTest
from cloudify_agent.tests.api.pm import only_os
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.internal.get_storage_directory',
       get_storage_directory)
@only_os('nt')
class TestNonSuckingServiceManagerDaemon(BaseDaemonProcessManagementTest,
                                         TestCase):

    @property
    def daemon_cls(self):
        return NonSuckingServiceManagerDaemon

    def test_configure(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        self.assertTrue(os.path.exists(daemon.config_path))

    def test_delete(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.stop()
        daemon.delete()
        self.assertFalse(os.path.exists(daemon.config_path))
        self.assertRaises(
            CommandExecutionException,
            self.runner.run,
            'sc getdisplayname {0}'.format(daemon.name))
