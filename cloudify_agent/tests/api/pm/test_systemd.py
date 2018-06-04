#########
# Copyright (c) 2018 Cloudify Platform Ltd. All rights reserved
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

import nose.tools
from cloudify_agent.api.pm.systemd import SystemDDaemon

from cloudify_agent.tests.api.pm import BaseDaemonProcessManagementTest
from cloudify_agent.tests.api.pm import only_os


@nose.tools.istest
@only_os('posix')
class TestSystemDDaemon(BaseDaemonProcessManagementTest):

    @property
    def daemon_cls(self):
        return SystemDDaemon
