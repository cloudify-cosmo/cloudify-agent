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

from cloudify.decorators import operation
from cloudify.amqp_client import get_client
from cloudify.models_states import AgentState
from cloudify import ctx, utils as cloudify_utils
from cloudify.exceptions import (CommandExecutionError,
                                 CommandExecutionException)
from cloudify.agent_utils import (create_agent_record,
                                  update_agent_record,
                                  delete_agent_rabbitmq_user)

from cloudify_agent.api import utils
from cloudify_agent.installer import script

from .config.agent_config import update_agent_runtime_properties
from .config.agent_config import create_agent_config_and_installer


@operation
@create_agent_config_and_installer(new_agent_config=True)
def create(cloudify_agent, installer, **_):
    # When not in "remote" mode, this operation is called only to set the
    # agent_config dict in the runtime properties
    create_agent_record(cloudify_agent)
    if cloudify_agent.has_installer:
        with script.install_script_path(cloudify_agent) as script_path:
            ctx.logger.info('Creating Agent {0}'.format(
                cloudify_agent['name']))
            try:
                installer.runner.run_script(script_path)
            except (CommandExecutionError, CommandExecutionException):
                ctx.logger.error("Failed creating agent; marking agent as "
                                 "failed")
                update_agent_record(cloudify_agent, AgentState.FAILED)
                raise
            ctx.logger.info(
                'Agent created, configured and started successfully'
            )
            update_agent_record(cloudify_agent, AgentState.STARTED)
    elif cloudify_agent.is_proxied:
        ctx.logger.info('Working in "proxied" mode')
    elif cloudify_agent.is_provided:
        ctx.logger.info('Working in "provided" mode')
        _, install_script_download_link = script.install_script_download_link(
            cloudify_agent
        )
        ctx.logger.info(
            'Agent config created. To configure/start the agent, download the '
            'following script: {0}'.format(install_script_download_link)
        )
        cloudify_agent['install_script_download_link'] = \
            install_script_download_link
        update_agent_runtime_properties(cloudify_agent)
        update_agent_record(cloudify_agent, AgentState.CREATED)


@operation
@create_agent_config_and_installer
def configure(cloudify_agent, installer, **_):
    ctx.logger.info('Configuring Agent {0}'.format(cloudify_agent['name']))
    update_agent_record(cloudify_agent, AgentState.CONFIGURING)
    try:
        installer.configure_agent()
    except CommandExecutionError as e:
        ctx.logger.error(str(e))
        update_agent_record(cloudify_agent, AgentState.FAILED)
        raise
    update_agent_record(cloudify_agent, AgentState.CONFIGURED)


@operation
@create_agent_config_and_installer
def start(cloudify_agent, **_):
    """
    Only called in "init_script"/"plugin" mode, where the agent is started
    externally (e.g. userdata script), and all we have to do is wait for it
    """
    update_agent_record(cloudify_agent, AgentState.STARTING)
    tenant = cloudify_utils.get_tenant()
    client = get_client(
        amqp_user=tenant['rabbitmq_username'],
        amqp_pass=tenant['rabbitmq_password'],
        amqp_vhost=tenant['rabbitmq_vhost']
    )
    agent_alive = utils.is_agent_alive(cloudify_agent['queue'], client)

    if not agent_alive:
        if ctx.operation.retry_number > 3:
            ctx.logger.warning('Waiting too long for Agent to start')
            update_agent_record(cloudify_agent, AgentState.NONRESPONSIVE)
        return ctx.operation.retry(
            message='Waiting for Agent to start...')

    ctx.logger.info('Agent has started')
    update_agent_record(cloudify_agent, AgentState.STARTED)
    if not cloudify_agent.is_provided:
        script.cleanup_scripts()


@operation
@create_agent_config_and_installer(validate_connection=False)
def stop(cloudify_agent, installer, **_):
    """
    Only called in "remote" mode - other modes stop via AMQP
    """
    ctx.logger.info('Stopping Agent {0}'.format(cloudify_agent['name']))
    update_agent_record(cloudify_agent, AgentState.STOPPING)
    installer.stop_agent()
    update_agent_record(cloudify_agent, AgentState.STOPPED)
    script.cleanup_scripts()


@operation
@create_agent_config_and_installer(validate_connection=False)
def delete(cloudify_agent, installer, **_):
    update_agent_record(cloudify_agent, AgentState.DELETING)
    # delete the runtime properties set on create
    if cloudify_agent.has_installer:
        ctx.logger.info('Deleting Agent {0}'.format(cloudify_agent['name']))
        installer.delete_agent()
    ctx.instance.runtime_properties.pop('cloudify_agent', None)
    ctx.instance.update()
    update_agent_record(cloudify_agent, AgentState.DELETED)

    # TODO: Delete the RabbitMQ queue after deleting the agent
    delete_agent_rabbitmq_user(cloudify_agent)


@operation
@create_agent_config_and_installer
def restart(cloudify_agent, installer, **_):
    # no need to handling remote_execution False because this operation is
    # not invoked in that case
    ctx.logger.info('Restarting Agent {0}'.format(cloudify_agent['name']))
    update_agent_record(cloudify_agent, AgentState.RESTARTING)
    try:
        installer.restart_agent()
    except CommandExecutionError as e:
        ctx.logger.error(str(e))
        update_agent_record(cloudify_agent, AgentState.FAILED)
        raise
    update_agent_record(cloudify_agent, AgentState.RESTARTED)
