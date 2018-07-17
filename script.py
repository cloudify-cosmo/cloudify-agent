#!/opt/cfy/embedded/bin/python

import os
import sys
import json
import click
import logging
import itertools
import tempfile
from contextlib import contextmanager
from distutils.version import LooseVersion

try:
    from cloudify_cli.env import get_rest_client, profile
except ImportError:
    get_rest_client = None
    profile = None

try:
    from cloudify_agent.api import utils
except ImportError:
    utils = None
try:
    from cloudify.celery.app import get_celery_app
except ImportError:
    get_celery_app = None

try:
    from manager_rest.storage.storage_manager import get_storage_manager
    from manager_rest.storage.resource_models import Node
    from manager_rest.storage.management_models import Tenant
    from manager_rest.config import instance
    from manager_rest.server import CloudifyFlaskApp
except ImportError:
    has_storage_manager = False
else:
    has_storage_manager = True


CHUNK_SIZE = 1000
DEPLOYMENT_PROXY = 'cloudify.nodes.DeploymentProxy'


def _check_status(rest_client):
    logging.info('Checking manager status: %s', profile.manager_ip)
    status = rest_client.manager.get_status()
    if status['status'] != 'running':
        raise ValueError('Unexpected manager status: %s', status['status'])
    logging.info('Manager status OK')


def _get_paginated_list(get, label, **kwargs):
    offset = 0
    kwargs.setdefault('_size', CHUNK_SIZE)
    while True:
        kwargs['_offset'] = offset
        chunk = get(**kwargs)
        pagination = chunk.metadata.pagination
        logging.info('Got %d of %d %s', len(chunk), pagination.total, label)
        yield chunk
        if pagination.total > offset + CHUNK_SIZE:
            offset += CHUNK_SIZE
        else:
            break


def _get_node_instances(rest_client, all_tenants):
    node_instances = _get_paginated_list(rest_client.node_instances.list,
                                         label='node instances',
                                         _all_tenants=all_tenants)
    return itertools.chain.from_iterable(node_instances)


def is_agent_instance(node_instance):
    return (node_instance.state == 'started' and
            'cloudify_agent' in node_instance.runtime_properties)


@contextmanager
def _celery_app(agent):
    broker_config = agent['broker_config']
    ssl_cert_path = _get_ssl_cert_path(broker_config)
    c = get_celery_app(
        broker_url=utils.internal.get_broker_url(broker_config),
        broker_ssl_enabled=broker_config.get('broker_ssl_enabled'),
        broker_ssl_cert_path=ssl_cert_path
    )
    try:
        yield c
    finally:
        if ssl_cert_path:
            os.remove(ssl_cert_path)


def _output_agent(agent, queue=None, timeout=5):
    with _celery_app(agent) as c:
        queue = queue or agent['queue']
        r = utils.get_agent_registered(queue, c, timeout=timeout)
        print 'name={0} queue={1} result={2}'.format(
            agent['name'], queue, bool(r))


def _get_ssl_cert_path(broker_config):
    if broker_config.get('broker_ssl_enabled'):
        fd, ssl_cert_path = tempfile.mkstemp()
        os.close(fd)
        with open(ssl_cert_path, 'w') as cert_file:
            cert_file.write(broker_config.get('broker_ssl_cert', ''))
        return ssl_cert_path
    else:
        return None


@click.group()
def main():
    pass


@main.command()
@click.option('-v', '--verbose', is_flag=True)
@click.option('--all-tenants/--no-all-tenants', is_flag=True, default=True,
              help='Update node instances of all tenants')
@click.option('--dry-run', is_flag=True, help="Don't actually update anything")
def show_agents(verbose, all_tenants, dry_run):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    rest_client = get_rest_client()
    _check_status(rest_client)
    node_instances = _get_node_instances(rest_client, all_tenants)
    agent_instances = itertools.ifilter(is_agent_instance, node_instances)

    upgrades = {}
    upgraded_agents = set()
    for inst in agent_instances:
        agent = inst.runtime_properties['cloudify_agent']
        upgrades.setdefault(
            agent['name'], (None, agent.get('version')))
        old_agent = inst.runtime_properties.get('old_cloudify_agent')
        if old_agent:
            upgrades[old_agent['name']] = agent['name'], agent.get('version')
            upgraded_agents.add(agent['name'])
    for a in upgraded_agents:
        upgrades.pop(a, None)

    for k, v in upgrades.items():
        name, version = v
        print '{0} {1} version={2}'.format(k, name or '', version)


@main.command()
@click.option('-v', '--verbose', is_flag=True)
@click.option('--all-tenants/--no-all-tenants', is_flag=True, default=True,
              help='Update node instances of all tenants')
@click.option('--dry-run', is_flag=True, help="Don't actually update anything")
def upgraded(verbose, all_tenants, dry_run):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    rest_client = get_rest_client()
    _check_status(rest_client)
    node_instances = _get_node_instances(rest_client, all_tenants)
    agent_instances = itertools.ifilter(is_agent_instance, node_instances)

    upgrades = {}
    for inst in agent_instances:
        if 'old_cloudify_agent' in inst.runtime_properties:
            agent = inst.runtime_properties['cloudify_agent']
            upgrades[inst.id] = agent['queue'], agent.get('version')

    for k, (queue, ver) in upgrades.items():
        print 'node-instance={0} queue={1} version={2}'.format(k, queue, ver)


def is_upgraded(instance):
    return 'old_cloudify_agent' in instance.runtime_properties

NODES_CACHE = {}


def _get_node(node_id, instance, rest_client):
    tenant_name = instance['tenant_name']
    deployment_id = instance.deployment_id
    node_name = node_id
    key = (tenant_name, deployment_id, node_name)
    if key not in NODES_CACHE:
        NODES_CACHE[key] = rest_client.nodes.get(
            node_id=node_id,
            deployment_id=deployment_id)
    return NODES_CACHE[key]


def find_deployment_proxy(instance, rest_client):
    for rel in instance.relationships:
        rel_node = _get_node(rel['target_name'], instance, rest_client)
        if DEPLOYMENT_PROXY in rel_node['type_hierarchy']:
            return rel_node


def is_proxied(instance, rest_client, host_type='cloudify.foreman.nodes.Host'):
    node = _get_node(instance['node_id'], instance, rest_client)
    if bool(find_deployment_proxy(instance, rest_client)):
        return True
    return host_type not in node['type_hierarchy']


def _output_instance(instance):
    queue = instance.runtime_properties['cloudify_agent'].get('queue')
    print instance.deployment_id, instance.id, queue


@main.command()
@click.option('-v', '--verbose', is_flag=True)
@click.option('--all-tenants/--no-all-tenants', is_flag=True, default=True,
              help='Update node instances of all tenants')
@click.option('--ignore-version-check', is_flag=True, default=True,
              help='Update node instances of all tenants')
@click.option('--host-type', default='cloudify.foreman.nodes.Host')
def to_upgrade(verbose, all_tenants, ignore_version_check, host_type):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    rest_client = get_rest_client()
    _check_status(rest_client)
    node_instances = _get_node_instances(rest_client, all_tenants)
    agent_instances = itertools.ifilter(is_agent_instance, node_instances)

    for inst in agent_instances:
        if is_upgraded(inst):
            continue
        if is_proxied(inst, rest_client, host_type=host_type):
            continue
        if not ignore_version_check:
            version = inst.runtime_properties['cloudify_agent'].get('version')
            if version and LooseVersion(version) >= LooseVersion('4.3'):
                continue
        _output_instance(inst)


@main.command()
@click.option('-v', '--verbose', is_flag=True)
@click.option('--all-tenants/--no-all-tenants', is_flag=True, default=True,
              help='Update node instances of all tenants')
@click.option('--host-type', default='cloudify.foreman.nodes.Host')
def find_proxied(verbose, all_tenants, host_type):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    rest_client = get_rest_client()
    _check_status(rest_client)
    node_instances = _get_node_instances(rest_client, all_tenants)
    agent_instances = itertools.ifilter(is_agent_instance, node_instances)

    for inst in agent_instances:
        if is_upgraded(inst):
            continue
        if not is_proxied(inst, rest_client, host_type=host_type):
            continue
        _output_instance(inst)


@main.command()
@click.argument('node_instance_id')
@click.option('-v', '--verbose', is_flag=True)
@click.option('--dry-run', is_flag=True, help="Don't actually update anything")
def fix_proxied(node_instance_id, verbose, dry_run):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    rest_client = get_rest_client()
    _check_status(rest_client)

    node_instance = rest_client.node_instances.get(node_instance_id)
    original_agent = node_instance.runtime_properties['cloudify_agent']
    original_queue = original_agent['queue']
    original_name = original_agent['name']

    # proxy = find_deployment_proxy(node_instance, rest_client)
    # deployment_id = proxy.properties['resource_config']['deployment']['id']
    agent_id = node_instance.runtime_properties['cloudify_agent']['queue']
    agent_node_instance = rest_client.node_instances.get(agent_id)
    agent = agent_node_instance.runtime_properties['cloudify_agent']

    queue, name = agent['queue'], agent['name']

    logging.info('%s: changing name from %s to %s',
                 node_instance.id, original_name, name)
    logging.info('%s: changing queue from %s to %s',
                 node_instance.id, original_queue, queue)
    node_instance.runtime_properties['cloudify_agent']['queue'] = queue
    node_instance.runtime_properties['cloudify_agent']['name'] = name
    if not dry_run:
        rest_client.node_instances.update(
            node_instance_id,
            runtime_properties=node_instance.runtime_properties,
            version=node_instance.version)


@main.command()
@click.option('-v', '--verbose', is_flag=True)
@click.option('-queue', '--queue')
@click.argument('infile', type=click.File())
def check(infile, queue, verbose):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    runtime_properties = json.load(infile)
    agent = runtime_properties['cloudify_agent']
    _output_agent(agent, queue=queue)


@main.command()
@click.argument('node_instance')
@click.option('--directory', help='Store runtime props as a <ID>.json file '
                                  'in this directory; otherwise output '
                                  'to stdout')
def get(node_instance, directory):
    rest_client = get_rest_client()
    ni = rest_client.node_instances.get(node_instance)
    if directory:
        with open(os.path.join(directory, '{0}.json'.format(ni.id)), 'w') as f:
            json.dump(ni.runtime_properties, f, indent=4, sort_keys=True)
    else:
        print json.dumps(ni.runtime_properties, indent=4, sort_keys=True)


@main.command()
@click.argument('node_instance')
@click.option('-v', '--verbose', is_flag=True)
@click.option('--path')
def put(node_instance, path, verbose):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    with open(path) as f:
        rp = json.load(f)

    rest_client = get_rest_client()
    ni = rest_client.node_instances.get(node_instance)
    with tempfile.NamedTemporaryFile(
            prefix='runtime-props-', delete=False) as f:
        json.dump(ni.runtime_properties, f, indent=4, sort_keys=True)
    logging.info('Backing up %s runtime properties to %s', ni.id, f.name)
    rest_client.node_instances.update(
        node_instance, runtime_properties=rp, version=ni.version)


@main.command()
@click.argument('infile', type=click.File())
def format_install_exec(infile):
    for i in infile:
        dep, inst, rest = i.split(' ', 2)
        click.echo('cfy executions start -d {0} install_new_agents -p node_instance_ids={1}'  # noqa
                  .format(dep, inst))


@main.command()
@click.argument('infile', type=click.File())
@click.option('--dry-run', is_flag=True, help="Don't actually update anything")
def format_update_proxy(infile, dry_run):
    for i in infile:
        dep, inst, rest = i.split(' ', 2)
        click.echo(
            '{0} fix_proxied {1}{2}'
            .format(sys.argv[0], '--dry-run ' if dry_run else '', inst))


@main.command()
@click.argument('node-id')
@click.option('--install-method', default='provided')
@click.option('-d', '--deployment-id', required=True)
@click.option('-t', '--tenant-id', required=True)
@click.option('-v', '--verbose', is_flag=True)
@click.option('--config-file', default='/opt/manager/cloudify-rest.conf')
def set_node_install_method(node_id, deployment_id, tenant_id, install_method,
                            verbose, config_file):
    if not has_storage_manager:
        raise RuntimeError('Use the restservice virtualenv')
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    instance.load_from_file(config_file)
    app = CloudifyFlaskApp()

    with app.app_context():
        sm = get_storage_manager()
        tenant = sm.get(Tenant, None, filters={'name': tenant_id})
        nodes = sm.list(Node, filters={
            'id': node_id,
            'deployment_id': deployment_id,
            '_tenant_id': tenant.id
        })
        if len(nodes) != 1:
            raise ValueError('Expected one node, found {0}'.format(len(nodes)))
        node = nodes[0]

        old_install_method = node.properties['agent_config']['install_method']
        node.properties['agent_config']['install_method'] = install_method
        logging.info(
            '%s: changing install_method from %s to %s',
            node_id,
            old_install_method,
            install_method)
        sm.update(node, modified_attrs=('properties', ))


if __name__ == '__main__':
    main()
