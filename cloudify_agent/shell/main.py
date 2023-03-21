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

import logging
import os

import click

from cloudify.utils import setup_logger

from cloudify_agent.api.utils import (
    get_agent_version,
    get_system_name,
    logger as api_utils_logger,
    get_rest_client,
)
from cloudify_agent.api.factory import DaemonFactory

# adding all of our commands.

from cloudify_agent.shell.commands import daemons
from cloudify_agent.shell.commands import configure
from cloudify_agent.shell.commands import cfy

_logger = setup_logger('cloudify_agent.shell.main',
                       logger_format='%(asctime)s [%(levelname)-5s] '
                                     '[%(name)s] %(message)s',
                       logger_level=logging.INFO)


def get_logger():
    return _logger


def show_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    ver = get_agent_version()
    logger = get_logger()
    logger.info('Cloudify Agent {0}'.format(ver))
    ctx.exit()


@cfy.group()
@click.option('--debug', default=False, is_flag=True)
@click.option('--version', is_flag=True, callback=show_version,
              expose_value=False, is_eager=True, help='Show version and exit')
def main(debug):
    if debug:

        # configure global logger level
        global _logger
        _logger.setLevel(logging.DEBUG)

        # configure api loggers so that there logging level does not rely
        # on imports from the shell modules
        api_utils_logger.setLevel(logging.DEBUG)


def _save_daemon(daemon):
    DaemonFactory(username=daemon.user).save(daemon)


def _parse_rest_hosts(ctx, param, value):
    return [host.strip() for host in value.split(',')]


@cfy.command('setup')
@click.option(
    '--name',
    help='The name of the agent',
)
@click.option(
    '--node-instance-id',
    help='ID of the current node instance (defaults to agent name)',
)
@click.option(
    '--rest-hosts',
    help='Comma-separated list of Cloudify Manager REST-service addresses',
    callback=_parse_rest_hosts,
)
@click.option(
    '--rest-port',
    help='Port to connect to the Cloudify Manager REST-service on',
)
@click.option(
    '--rest-ca-path',
    help='Path to the CA certificate of the Cloudify Manager REST-service',
)
@click.option(
    '--tenant-name',
    help='Name of the tenant this agent belongs to',
)
@click.option(
    '--rest-token',
    help='Authentication token for the REST-service',
)
@click.option(
    '--agent-dir',
    help='Directory to install the agent in',
)
@click.option(
    '--process-management',
    help='Process management system to use for the agent daemon',
)
@click.option(
    '--bypass-maintenance',
    is_flag=True,
    default=False,
    help='Install while the Cloudify Manager is in maintenance mode',
)
def setup(
    name,
    rest_hosts,
    rest_port,
    rest_ca_path,
    tenant_name,
    rest_token,
    agent_dir,
    process_management,
    bypass_maintenance=False,
    node_instance_id=None,
):
    """Prepare the agent, storing the agent settings"""
    if node_instance_id is None:
        node_instance_id = name
    client = get_rest_client(
        rest_host=rest_hosts,
        rest_port=rest_port,
        rest_token=rest_token,
        rest_tenant=tenant_name,
        ssl_cert_path=rest_ca_path,
        bypass_maintenance_mode=bypass_maintenance,
    )
    inst = client.node_instances.get(
        node_instance_id,
        evaluate_functions=True,
    )
    agent = client.agents.get(name)
    agent_config = inst.runtime_properties['cloudify_agent']
    agent_config['agent_dir'] = agent_dir
    client.node_instances.update(
        inst.id,
        version=inst.version,
        runtime_properties=inst.runtime_properties,
    )
    network = agent_config.get('network') or 'default'

    broker_certs = set()
    brokers = client.manager.get_brokers()
    for broker in brokers:
        cert = broker.ca_cert_content
        if cert:
            broker_certs.add(cert.strip())
    broker_ssl_cert_path = None
    if broker_certs:
        broker_ssl_cert_path = os.path.join(
            agent_dir, 'cloudify', 'ssl', 'broker_cert.pem')
        with open(broker_ssl_cert_path, 'w') as f:
            f.write('\n'.join(broker_certs))

    click.echo('Creating...')
    daemon = DaemonFactory().new(
        logger=get_logger(),
        name=name,
        broker_ip=[
            broker.networks.get(network) or broker.host
            for broker in brokers
        ],
        local_rest_cert_file=os.path.join(
            agent_dir, 'cloudify', 'ssl', 'cloudify_internal_cert.pem'),
        broker_user=agent.rabbitmq_username,
        broker_pass=agent.rabbitmq_password,
        broker_vhost=agent_config['tenant']['rabbitmq_vhost'],
        broker_ssl_enabled=True,
        broker_ssl_cert_path=broker_ssl_cert_path,
        agent_dir=agent_dir,
        deployment_id=inst.deployment_id,
        process_management=process_management,
        user=agent_config['user'],
        queue=agent_config['queue'],
        heartbeat=agent_config.get('heartbeat'),
        extra_env=agent_config.get('env', {}),
        log_level=agent_config.get('log_level'),
        log_max_bytes=agent_config.get('log_max_bytes'),
        log_max_history=agent_config.get('log_max_history'),
        network=network,
        min_workers=agent_config.get('min_workers'),
        max_workers=agent_config.get('max_workers'),
        executable_temp_path=agent_config.get('executable_temp_path'),
        resources_root=os.path.join(agent_dir, 'resources'),
    )
    _save_daemon(daemon)
    daemon.create_broker_conf()

    version = get_agent_version()
    system = get_system_name()
    click.echo(f'Agent version: {version}, system: {system}')
    client.agents.update(name, version=version, system=system)

    click.echo(f'Successfully created daemon: {daemon.name}')


@cfy.group(name='daemons')
def daemon_sub_command():
    pass


@cfy.group(name='plugins')
def plugins_sub_command():
    pass


main.add_command(setup)
main.add_command(configure.configure)

daemon_sub_command.add_command(daemons.create)
daemon_sub_command.add_command(daemons.start)
daemon_sub_command.add_command(daemons.stop)
daemon_sub_command.add_command(daemons.delete)
daemon_sub_command.add_command(daemons.restart)
daemon_sub_command.add_command(daemons.inspect)
daemon_sub_command.add_command(daemons.ls)
daemon_sub_command.add_command(daemons.status)

main.add_command(daemon_sub_command)
main.add_command(plugins_sub_command)
