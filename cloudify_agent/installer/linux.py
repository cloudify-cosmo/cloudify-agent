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

from cloudify_agent.installer import LinuxInstallerMixin
from cloudify_agent.installer import LocalInstallerMixin
from cloudify_agent.installer import RemoteInstallerMixin


class RemoteLinuxAgentInstaller(LinuxInstallerMixin, RemoteInstallerMixin):

    def __init__(self, cloudify_agent, runner, logger=None):
        super(RemoteLinuxAgentInstaller, self).__init__(cloudify_agent, logger)
        self._runner = runner

    @property
    def runner(self):
        return self._runner


class LocalLinuxAgentInstaller(LinuxInstallerMixin, LocalInstallerMixin):

    def __init__(self, cloudify_agent, logger=None):
        super(LocalLinuxAgentInstaller, self).__init__(
            cloudify_agent, logger
        )
