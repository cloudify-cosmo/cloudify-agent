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
import time

from cloudify import ctx
from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError
from cloudify_agent.app import app
from cloudify_agent.api.utils import get_agent_registered
from openstack_plugin_common import with_nova_client
from nova_plugin.server import get_server_by_context, SERVER_STATUS_ACTIVE


INTERVAL = 10
VM_ATTEMPTS = 20
AGENT_ATTEMPTS = 20


@operation
@with_nova_client
def reboot(nova_client, **_):
    server = get_server_by_context(nova_client)
    ctx.logger.info('Rebooting machine')
    nova_client.servers.reboot(server)
    i = 0
    vm_started = False
    while i < VM_ATTEMPTS and not vm_started:
        ctx.logger.info('Waiting for vm to reboot, attempt {0}'.format(i + 1))
        time.sleep(INTERVAL)
        server = get_server_by_context(nova_client)
        vm_started = server.status == SERVER_STATUS_ACTIVE
        i += 1
    if vm_started:
        ctx.logger.info('Machine rebooted')
    else:
        raise NonRecoverableError('Could not reboot machine')

    agent_name = ctx.instance.runtime_properties['cloudify_agent']['name']
    i = 0
    agent_alive = False
    while i < AGENT_ATTEMPTS and not agent_alive:
        ctx.logger.info('Waiting for agent, attempt {0}'.format(i + 1))
        time.sleep(INTERVAL)
        agent_alive = get_agent_registered(agent_name, app)
        i += 1
    if agent_alive:
        ctx.logger.info('Agent started')
    else:
        raise NonRecoverableError('Agent did not start')
