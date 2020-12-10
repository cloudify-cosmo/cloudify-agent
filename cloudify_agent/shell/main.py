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

import getpass
import json
import os
import sys

import logging

import click

from cloudify.utils import setup_logger

from cloudify_agent.api.utils import (
    get_agent_version,
    logger as api_utils_logger,
    get_rest_client,
    internal
)

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


@cfy.group(name='daemons')
def daemon_sub_command():
    pass


@cfy.group(name='plugins')
def plugins_sub_command():
    pass


@main.command()
@click.option('--ca-cert', type=click.Path())
@click.option('--node-instance-id')
@click.option('--manager-ip')
@click.option('--token')
def setup(manager_ip, node_instance_id, token, ca_cert):
    client = get_rest_client(
        [manager_ip], 53333, token, 'default_tenant', ca_cert)
    storage_dir = internal.get_storage_directory()
    fn = os.path.join(
        storage_dir,
        '{0}.json'.format(node_instance_id)
    )
    if not os.path.isdir(storage_dir):
        os.makedirs(storage_dir)
    agent_dir = os.path.join(os.path.expanduser('~'), node_instance_id)
    cert_fn = os.path.join(agent_dir, 'ca_cert.pem')

    ni = client.node_instances.get(node_instance_id)
    agent_config = ni.runtime_properties.get('cloudify_agent') or {}
    ag = client.agents.get(node_instance_id)
    brokers = client.manager.get_brokers()

    agent_config['process_management'] = \
        agent_config['process_management']['name']
    agent_config['local_rest_cert_file'] = cert_fn
    agent_config['user'] = getpass.getuser()
    agent_config['agent_dir'] = agent_dir
    network = agent_config['network']
    agent_config['rest_host'] = [
        m.networks.get(network) for m in client.manager.get_managers()]
    broker_config = {
        'broker_cert_path': cert_fn,
        'broker_ssl_enabled': True,
        'broker_username': ag.rabbitmq_username,
        'broker_password': ag.rabbitmq_password,
        'broker_hostname': [b.networks.get(network) for b in brokers],
        'broker_vhost': agent_config.pop('vhost'),
    }
    del agent_config['tenant']

    with open(os.path.join(agent_dir, 'broker_config.json'), 'w') as f:
        json.dump(broker_config, f, indent=4, sort_keys=True)

    with open(cert_fn, 'w') as f:
        f.write(agent_config.pop('broker_ssl_cert'))
        f.write('\n')
        f.write(agent_config.pop('rest_ssl_cert'))

    with open(fn, 'w') as f:
        json.dump(agent_config, f, indent=4, sort_keys=True)


@main.command()
def start():
    os.execve(sys.executable, [
        sys.executable, '-m', 'cloudify_agent.worker'
    ], os.environ)


main.add_command(start)
main.add_command(setup)

main.add_command(configure.configure)

daemon_sub_command.add_command(daemons.create)
daemon_sub_command.add_command(daemons.configure)
daemon_sub_command.add_command(daemons.start)
daemon_sub_command.add_command(daemons.stop)
daemon_sub_command.add_command(daemons.delete)
daemon_sub_command.add_command(daemons.restart)
daemon_sub_command.add_command(daemons.inspect)
daemon_sub_command.add_command(daemons.ls)
daemon_sub_command.add_command(daemons.status)

main.add_command(daemon_sub_command)
main.add_command(plugins_sub_command)
