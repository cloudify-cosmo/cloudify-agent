#########
# Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
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
from cloudify import ctx

from cloudify_agent.installer import init_agent_installer
from cloudify_agent.api import utils
from cloudify_agent.app import app


@operation
@init_agent_installer
def create(cloudify_agent, **_):

    # save runtime properties immediately so that they will be available
    # to other operation even in case the create failed.
    ctx.instance.runtime_properties['cloudify_agent'] = cloudify_agent

    remote_execution = ctx.node.properties['remote_execution']
    if remote_execution:
        ctx.logger.info('Creating Agent {0}'.format(cloudify_agent['name']))
        ctx.installer.create_agent()


@operation
@init_agent_installer
def configure(cloudify_agent, **_):
    ctx.logger.info('Configuring Agent {0}'.format(cloudify_agent['name']))
    ctx.installer.configure_agent()


@operation
@init_agent_installer
def start(cloudify_agent, **_):

    remote_execution = ctx.node.properties['remote_execution']
    if remote_execution:
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
    del ctx.instance.runtime_properties['cloudify_agent']


@operation
@init_agent_installer
def restart(cloudify_agent, **_):
    ctx.logger.info('Restarting Agent {0}'.format(cloudify_agent['name']))
    ctx.installer.restart_agent()
