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

from cloudify import ctx
from cloudify.utils import LocalCommandRunner
from cloudify.exceptions import CommandExecutionError

from cloudify_agent.installer.linux import LocalLinuxAgentInstaller
from cloudify_agent.installer.linux import RemoteLinuxAgentInstaller
from cloudify_agent.installer.windows import LocalWindowsAgentInstaller
from cloudify_agent.installer.windows import RemoteWindowsAgentInstaller
from cloudify_agent.installer.runners.fabric_runner import FabricRunner
from cloudify_agent.installer.runners.winrm_runner import WinRMRunner
from cloudify_agent.installer.runners.stub_runner import StubRunner


def get_installer(cloudify_agent, runner):
    if cloudify_agent.is_local:
        if os.name == 'nt':
            installer = LocalWindowsAgentInstaller(cloudify_agent, ctx.logger)
        else:
            installer = LocalLinuxAgentInstaller(cloudify_agent, ctx.logger)
    elif cloudify_agent.is_windows:
        installer = RemoteWindowsAgentInstaller(
            cloudify_agent, runner, ctx.logger)
    else:
        installer = RemoteLinuxAgentInstaller(
            cloudify_agent, runner, ctx.logger)
    return installer


def create_runner(agent_config, validate_connection):
    if agent_config.is_local:
        runner = LocalCommandRunner(logger=ctx.logger)
    elif not agent_config.is_remote:
        runner = StubRunner()
    else:
        host = agent_config['ip']
        try:
            if agent_config.is_windows:
                runner = WinRMRunner(
                    host=host,
                    port=agent_config.get('port'),
                    user=agent_config['user'],
                    password=agent_config.get('password'),
                    protocol=agent_config.get('protocol'),
                    uri=agent_config.get('uri'),
                    transport=agent_config.get('transport'),
                    logger=ctx.logger,
                    tmpdir=agent_config.tmpdir,
                    validate_connection=validate_connection)
            else:
                runner = FabricRunner(
                    host=host,
                    port=agent_config.get('port'),
                    user=agent_config['user'],
                    key=agent_config.get('key'),
                    password=agent_config.get('password'),
                    fabric_env=agent_config.get('fabric_env'),
                    logger=ctx.logger,
                    tmpdir=agent_config.tmpdir,
                    validate_connection=validate_connection)
        except CommandExecutionError as e:
            message = e.error
            if not message:
                message = 'Failed connecting to host on {0}'.format(
                    host)
            return ctx.operation.retry(message=message)

    return runner
