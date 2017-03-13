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
from cloudify import context

from cloudify_agent.installer.linux import LocalLinuxAgentInstaller
from cloudify_agent.installer.linux import RemoteLinuxAgentInstaller
from cloudify_agent.installer.windows import LocalWindowsAgentInstaller
from cloudify_agent.installer.windows import RemoteWindowsAgentInstaller
from cloudify_agent.installer.runners.fabric_runner import FabricRunner
from cloudify_agent.installer.runners.winrm_runner import WinRMRunner
from cloudify_agent.installer.runners.stub_runner import StubRunner
from cloudify_agent.installer.config import configuration
from cloudify_agent.api import utils


def prepare_local_installer(cloudify_agent, logger=None):
    if os.name == 'nt':
        installer = LocalWindowsAgentInstaller(cloudify_agent, logger)
    else:
        installer = LocalLinuxAgentInstaller(cloudify_agent, logger)
    return installer


def init_agent_installer(func=None, validate_connection=True):

    if func is not None:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cloudify_agent = kwargs.get('cloudify_agent') or {}
            agent_config = kwargs.get('agent_config') or {}
            cloudify_agent.update(agent_config)

            # first prepare all connection details
            configuration.prepare_connection(cloudify_agent)

            # create the correct runner according to os
            # and local/remote execution. we need this runner now because it
            # will be used to determine the agent basedir in case it wasn't
            # explicitly set
            if cloudify_agent['local']:
                runner = LocalCommandRunner(logger=ctx.logger)
            elif cloudify_agent['remote_execution'] is False:
                runner = StubRunner()
            else:
                host = cloudify_agent['ip']
                try:
                    if cloudify_agent['windows']:
                        runner = WinRMRunner(
                            host=host,
                            port=cloudify_agent.get('port'),
                            user=cloudify_agent['user'],
                            password=cloudify_agent['password'],
                            protocol=cloudify_agent.get('protocol'),
                            uri=cloudify_agent.get('uri'),
                            logger=ctx.logger,
                            validate_connection=validate_connection)
                    else:
                        runner = FabricRunner(
                            host=host,
                            port=cloudify_agent.get('port'),
                            user=cloudify_agent['user'],
                            key=cloudify_agent.get('key'),
                            password=cloudify_agent.get('password'),
                            fabric_env=cloudify_agent.get('fabric_env'),
                            logger=ctx.logger,
                            validate_connection=validate_connection)
                except CommandExecutionError as e:
                    message = e.error
                    if not message:
                        message = 'Failed connecting to host on {0}'.format(
                            host)
                    return ctx.operation.retry(message=message)

            # now we can create all other agent attributes
            configuration.prepare_agent(cloudify_agent, runner)

            # create the correct installer according to os
            # and local/remote execution
            if cloudify_agent['local']:
                installer = prepare_local_installer(cloudify_agent, ctx.logger)
            elif cloudify_agent['windows']:
                installer = RemoteWindowsAgentInstaller(
                    cloudify_agent, runner, ctx.logger)
            else:
                installer = RemoteLinuxAgentInstaller(
                    cloudify_agent, runner, ctx.logger)

            kwargs['cloudify_agent'] = cloudify_agent
            kwargs['installer'] = installer

            try:
                return func(*args, **kwargs)
            finally:
                if hasattr(installer.runner, 'close'):
                    installer.runner.close()

        return wrapper
    else:
        def partial_wrapper(fn):
            return init_agent_installer(
                fn, validate_connection=validate_connection)
        return partial_wrapper


@operation
@init_agent_installer
def create(cloudify_agent, installer, **_):
    if ctx.type == context.NODE_INSTANCE:

        # save runtime properties immediately so that they will be available
        # to other operation even in case the create operation failed.
        ctx.instance.runtime_properties['cloudify_agent'] = cloudify_agent
        ctx.instance.update()

        if cloudify_agent['remote_execution']:
            ctx.logger.info('Creating Agent {0}'.format(
                cloudify_agent['name']))
            installer.create_agent()
    else:
        ctx.logger.info('Creating Agent {0}'.format(cloudify_agent['name']))
        installer.create_agent()


@operation
@init_agent_installer
def configure(cloudify_agent, installer, **_):

    if ctx.type == context.NODE_INSTANCE:
        if cloudify_agent['remote_execution']:
            ctx.logger.info('Configuring Agent {0}'.format(
                cloudify_agent['name']))
            installer.configure_agent()
    else:
        ctx.logger.info('Configuring Agent {0}'.format(cloudify_agent['name']))
        installer.configure_agent()


@operation
@init_agent_installer
def start(cloudify_agent, installer, **_):

    if ctx.type == context.NODE_INSTANCE:
        if cloudify_agent['remote_execution']:
            ctx.logger.info('Starting Agent {0}'.format(
                cloudify_agent['name']))
            installer.start_agent()
        else:
            # if remote_execution is False, and this operation was invoked
            # (install_agent is True), it means that some other process is
            # installing the agent (e.g userdata). All that is left for us
            # to do is wait for the agent to start.

            # celery is imported here since it's only used in this method
            # and we can't assume it's always available
            from cloudify_agent.app import app as celery_client
            registered = utils.get_agent_registered(cloudify_agent['name'],
                                                    celery_client)
            if registered:
                ctx.logger.info('Agent has started')
            else:
                return ctx.operation.retry(
                    message='Waiting for Agent to start...')
    else:
        ctx.logger.info('Starting Agent {0}'.format(cloudify_agent['name']))
        installer.start_agent()


@operation
@init_agent_installer(validate_connection=False)
def stop(cloudify_agent, installer, **_):

    # no need to handling remote_execution False because this operation is
    # not invoked in that case
    ctx.logger.info('Stopping Agent {0}'.format(cloudify_agent['name']))
    installer.stop_agent()


@operation
@init_agent_installer(validate_connection=False)
def delete(cloudify_agent, installer, **_):

    if ctx.type == context.NODE_INSTANCE:
        # delete the runtime properties set on create
        ctx.instance.runtime_properties.pop('cloudify_agent', None)
        if cloudify_agent['remote_execution']:
            ctx.logger.info('Deleting Agent {0}'.format(
                cloudify_agent['name']))
            installer.delete_agent()
    else:
        ctx.logger.info('Deleting Agent {0}'.format(cloudify_agent['name']))
        installer.delete_agent()


@operation
@init_agent_installer
def restart(cloudify_agent, installer, **_):

    # no need to handling remote_execution False because this operation is
    # not invoked in that case
    ctx.logger.info('Restarting Agent {0}'.format(cloudify_agent['name']))
    installer.restart_agent()
