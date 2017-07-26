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

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.celery.app import get_celery_app
from cloudify.exceptions import CommandExecutionError

from cloudify_agent.api import utils

from cloudify_agent.installer.script import install_script_path
from .config.agent_config import create_agent_config_and_installer


@operation
@create_agent_config_and_installer(new_agent_config=True)
def create(cloudify_agent, installer, **_):
    if cloudify_agent['remote_execution']:
        with install_script_path(cloudify_agent) as script_path:
            ctx.logger.info('Creating Agent {0}'.format(
                cloudify_agent['name']))
            try:
                response = installer.runner.run_script(script_path)
                output = response.std_out
                if output:
                    for line in output.splitlines():
                        ctx.logger.info(line)
            except CommandExecutionError, e:
                ctx.logger.error(str(e))
                raise
            ctx.logger.info(
                'Agent created, configured and started successfully'
            )


@operation
@create_agent_config_and_installer
def configure(cloudify_agent, installer, **_):
    if cloudify_agent['remote_execution']:
        ctx.logger.info('Configuring Agent {0}'.format(cloudify_agent['name']))
        installer.configure_agent()


@operation
@create_agent_config_and_installer
def start(cloudify_agent, installer, **_):
    if cloudify_agent['remote_execution']:
        ctx.logger.info('Starting Agent {0}'.format(cloudify_agent['name']))
        installer.start_agent()
    else:
        # if remote_execution is False, and this operation was invoked
        # (install_agent is True), it means that some other process is
        # installing the agent (e.g userdata). All that is left for us
        # to do is wait for the agent to start.

        celery_client = get_celery_app(
            tenant=cloudify_agent['rest_tenant'],
            target=cloudify_agent['queue']
        )
        registered = utils.get_agent_registered(cloudify_agent['name'],
                                                celery_client)
        if registered:
            ctx.logger.info('Agent has started')
        else:
            return ctx.operation.retry(
                message='Waiting for Agent to start...')


@operation
@create_agent_config_and_installer(validate_connection=False)
def stop(cloudify_agent, installer, **_):
    # no need to handling remote_execution False because this operation is
    # not invoked in that case
    ctx.logger.info('Stopping Agent {0}'.format(cloudify_agent['name']))
    installer.stop_agent()


@operation
@create_agent_config_and_installer(validate_connection=False)
def delete(cloudify_agent, installer, **_):
    # delete the runtime properties set on create
    ctx.instance.runtime_properties.pop('cloudify_agent', None)
    if cloudify_agent['remote_execution']:
        ctx.logger.info('Deleting Agent {0}'.format(cloudify_agent['name']))
        installer.delete_agent()


@operation
@create_agent_config_and_installer
def restart(cloudify_agent, installer, **_):
    # no need to handling remote_execution False because this operation is
    # not invoked in that case
    ctx.logger.info('Restarting Agent {0}'.format(cloudify_agent['name']))
    installer.restart_agent()
