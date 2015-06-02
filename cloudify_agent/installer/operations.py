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
from functools import wraps

from cloudify.decorators import operation
from cloudify import ctx
from cloudify.exceptions import CommandExecutionError
from cloudify.utils import LocalCommandRunner
from cloudify.state import current_ctx
from cloudify import context

from cloudify_agent.installer.linux import LocalLinuxAgentInstaller
from cloudify_agent.installer.linux import RemoteLinuxAgentInstaller
from cloudify_agent.installer.windows import LocalWindowsAgentInstaller
from cloudify_agent.installer.windows import RemoteWindowsAgentInstaller
from cloudify_agent.installer.runners import fabric_runner
from cloudify_agent.installer.runners import winrm_runner
from cloudify_agent.installer.config import configuration
from cloudify_agent.api import utils
from cloudify_agent.app import app


def init_agent_installer(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        cloudify_agent = kwargs.get('cloudify_agent', {})

        # first prepare all connection details
        configuration.prepare_connection(cloudify_agent)

        # create the correct runner according to os
        # and local/remote execution. we need this runner now because it
        # will be used to determine the agent basedir in case it wasn't
        # explicitly set
        if cloudify_agent['local']:
            runner = LocalCommandRunner(logger=ctx.logger)
        else:
            try:
                if cloudify_agent['windows']:
                    runner = winrm_runner.WinRMRunner(
                        host=cloudify_agent['ip'],
                        user=cloudify_agent['user'],
                        password=cloudify_agent['password'],
                        port=cloudify_agent.get('port'),
                        protocol=cloudify_agent.get('protocol'),
                        uri=cloudify_agent.get('user'),
                        logger=ctx.logger)
                else:
                    runner = fabric_runner.FabricRunner(
                        logger=ctx.logger,
                        host=cloudify_agent['ip'],
                        user=cloudify_agent['user'],
                        port=cloudify_agent.get('port'),
                        key=cloudify_agent.get('key'),
                        password=cloudify_agent.get('password'),
                        fabric_env=cloudify_agent.get('fabric_env'))
            except CommandExecutionError as e:
                return ctx.operation.retry(message=e.error,
                                           retry_after=5)

        setattr(current_ctx.get_ctx(), 'runner', runner)

        # now we can create all other agent attributes
        configuration.prepare_agent(cloudify_agent)

        # create the correct installer according to os
        # and local/remote execution
        if cloudify_agent['local']:
            if os.name == 'nt':
                installer = LocalWindowsAgentInstaller(
                    cloudify_agent, ctx.logger)
            else:
                installer = LocalLinuxAgentInstaller(
                    cloudify_agent, ctx.logger)
        elif cloudify_agent['windows']:
            installer = RemoteWindowsAgentInstaller(
                cloudify_agent, ctx.logger)
        else:
            installer = RemoteLinuxAgentInstaller(
                cloudify_agent, ctx.logger)

        setattr(current_ctx.get_ctx(), 'installer', installer)

        kwargs['cloudify_agent'] = cloudify_agent

        try:
            return func(*args, **kwargs)
        finally:
            # we need to close fabric connection
            if isinstance(installer, RemoteLinuxAgentInstaller):
                installer.runner.close()

    return wrapper


@operation
@init_agent_installer
def create(cloudify_agent, **_):

    # save runtime properties immediately so that they will be available
    # to other operation even in case the create failed.
    if ctx.type == context.NODE_INSTANCE:
        ctx.instance.runtime_properties['cloudify_agent'] = cloudify_agent
        remote_execution = ctx.node.properties['remote_execution']
    else:
        remote_execution = False

    if cloudify_agent['local'] or remote_execution:
        ctx.logger.info('Creating Agent {0}'.format(cloudify_agent['name']))
        ctx.installer.create_agent()


@operation
@init_agent_installer
def configure(cloudify_agent, **_):
    if ctx.type == context.NODE_INSTANCE:
        remote_execution = ctx.node.properties['remote_execution']
    else:
        remote_execution = False

    if cloudify_agent['local'] or remote_execution:
        ctx.logger.info('Configuring Agent {0}'.format(cloudify_agent['name']))
        ctx.installer.configure_agent()


@operation
@init_agent_installer
def start(cloudify_agent, **_):

    if ctx.type == context.NODE_INSTANCE:
        remote_execution = ctx.node.properties['remote_execution']
    else:
        remote_execution = False

    if cloudify_agent['local'] or remote_execution:
        ctx.logger.info('Starting Agent {0}'.format(cloudify_agent['name']))
        ctx.installer.start_agent()
    stats = utils.get_agent_stats(cloudify_agent['name'], app)
    if stats:
        ctx.logger.info('Agent has started')
    else:
        return ctx.operation.retry(
            message='Waiting for Agent to start...',
            retry_after=5)


@operation
@init_agent_installer
def stop(cloudify_agent, **_):
    ctx.logger.info('Stopping Agent {0}'.format(cloudify_agent['name']))
    ctx.installer.stop_agent()


@operation
@init_agent_installer
def delete(cloudify_agent, **_):
    ctx.logger.info('Deleting Agent {0}'.format(cloudify_agent['name']))
    ctx.installer.delete_agent()

    # delete the runtime properties set on create
    if ctx.type == context.NODE_INSTANCE:
        del ctx.instance.runtime_properties['cloudify_agent']


@operation
@init_agent_installer
def restart(cloudify_agent, **_):
    ctx.logger.info('Restarting Agent {0}'.format(cloudify_agent['name']))
    ctx.installer.restart_agent()
