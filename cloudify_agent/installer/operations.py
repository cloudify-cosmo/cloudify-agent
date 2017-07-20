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

from tempfile import NamedTemporaryFile

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.celery.app import get_celery_app
from cloudify.exceptions import CommandExecutionError

from cloudify_agent.api import utils

from cloudify_agent.installer.script import get_init_script
from .config.agent_config import create_agent_config_and_installer


@operation
@create_agent_config_and_installer(new_agent=True)
def create(cloudify_agent, installer, **_):
    # save runtime properties immediately so that they will be available
    # to other operation even in case the create operation failed.
    ctx.instance.runtime_properties['cloudify_agent'] = cloudify_agent
    ctx.instance.update()

    script = get_init_script(cloudify_agent)
    with NamedTemporaryFile() as f:
        f.write(script)
        f.flush()

        if cloudify_agent['remote_execution']:
            ctx.logger.info('Creating Agent {0}'.format(
                cloudify_agent['name']))
            try:
                response = installer.runner.run_script(f.name)
                output = response.std_out
                if output:
                    installer.logger.warning('Output:\n{0}'.format(output))
                    for line in output.splitlines():
                        installer.logger.info(line)
            except CommandExecutionError, e:
                ctx.logger.error(str(e))
                raise


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
        ctx.logger.info('Starting Agent {0}'.format(
            cloudify_agent['name']))
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
        ctx.logger.info('Deleting Agent {0}'.format(
            cloudify_agent['name']))
        installer.delete_agent()


@operation
@create_agent_config_and_installer
def restart(cloudify_agent, installer, **_):
    # no need to handling remote_execution False because this operation is
    # not invoked in that case
    ctx.logger.info('Restarting Agent {0}'.format(cloudify_agent['name']))
    installer.restart_agent()
