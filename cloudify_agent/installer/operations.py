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

from cloudify_agent.installer import script
from .config.agent_config import update_agent_runtime_properties
from .config.agent_config import create_agent_config_and_installer


@operation
@create_agent_config_and_installer(new_agent_config=True)
def create(cloudify_agent, installer, **_):
    # When not in "remote" mode, this operation is called only to set the
    # agent_config dict in the runtime properties
    if cloudify_agent.has_installer:
        with script.install_script_path(cloudify_agent) as script_path:
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


@operation
@create_agent_config_and_installer
def configure(cloudify_agent, installer, **_):
    ctx.logger.info('Configuring Agent {0}'.format(cloudify_agent['name']))
    installer.configure_agent()


@operation
@create_agent_config_and_installer
def start(cloudify_agent, **_):
    """
    Only called in "init_script"/"plugin" mode, where the agent is started
    externally (e.g. userdata script), and all we have to do is wait for it
    """
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
    """
    Only called in "remote" mode - other modes stop via AMQP
    """
    ctx.logger.info('Stopping Agent {0}'.format(cloudify_agent['name']))
    installer.stop_agent()


@operation
@create_agent_config_and_installer(validate_connection=False)
def delete(cloudify_agent, installer, **_):
    # delete the runtime properties set on create
    ctx.instance.runtime_properties.pop('cloudify_agent', None)
    if cloudify_agent.has_installer:
        ctx.logger.info('Deleting Agent {0}'.format(cloudify_agent['name']))
        installer.delete_agent()


@operation
@create_agent_config_and_installer
def restart(cloudify_agent, installer, **_):
    # no need to handling remote_execution False because this operation is
    # not invoked in that case
    ctx.logger.info('Restarting Agent {0}'.format(cloudify_agent['name']))
    installer.restart_agent()
