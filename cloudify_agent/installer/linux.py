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

from setuptools import archive_util


from cloudify_agent.installer import AgentInstaller
from cloudify_agent.installer import LinuxMixin, LocalMixin


class RemoteLinuxAgentInstaller(AgentInstaller, LinuxMixin):

    def __init__(self, cloudify_agent, logger=None):
        super(RemoteLinuxAgentInstaller, self).__init__(
            cloudify_agent, logger)

        # importing fabric stuff is a bit expensive and kind of shaky
        # because the import may fail on windows boxes that don't the pywin32
        # extensions installed. so lets import only when we really have to.
        from cloudify_agent.installer.runners.fabric_runner \
            import FabricRunner
        self._runner = FabricRunner(
            logger=self.logger,
            host=cloudify_agent['ip'],
            user=cloudify_agent['user'],
            port=cloudify_agent.get('port'),
            key=cloudify_agent.get('key'),
            password=cloudify_agent.get('password'),
            fabric_env=cloudify_agent.get('fabric_env'))

    def extract(self, archive, destination):
        return self.runner.untar(archive, destination)

    @property
    def runner(self):
        return self._runner


class LocalLinuxAgentInstaller(AgentInstaller, LocalMixin, LinuxMixin):

    def __init__(self, cloudify_agent, logger=None):
        super(LocalLinuxAgentInstaller, self).__init__(
            cloudify_agent, logger
        )

    def extract(self, archive, destination):
        self.logger.debug('Extracting {0} to {1}'
                          .format(archive, destination))
        archive_util.unpack_zipfile(archive, destination)
        return destination
