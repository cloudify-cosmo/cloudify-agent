#!/opt/mgmtworker/env/bin/python

import os
import json
import click
import logging
import itertools
import tempfile
from contextlib import contextmanager

from cloudify_cli.env import get_rest_client, profile
from cloudify_agent.api import utils
from cloudify.celery.app import get_celery_app

CHUNK_SIZE = 1000


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
    return 'cloudify_agent' in node_instance.runtime_properties


class C(object):
    logger = logging.getLogger()

    class B(object):
        def broker_config(self):
            return {}
    bootstrap_context = B()


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


def _output_agent(agent):
    with _celery_app(agent) as c:
        print agent['queue'], utils.get_agent_registered(agent['queue'], c)


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
def find(verbose, all_tenants, dry_run):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    rest_client = get_rest_client()
    _check_status(rest_client)
    node_instances = _get_node_instances(rest_client, all_tenants)
    agent_instances = itertools.ifilter(is_agent_instance, node_instances)

    upgrades = {}
    for inst in agent_instances:
        agent = inst.runtime_properties['cloudify_agent']
        old_agent = inst.runtime_properties.get('old_cloudify_agent')
        if old_agent:
            upgrades[old_agent['name']] = agent['name']
    print json.dumps(upgrades, indent=4)


@main.command()
@click.argument('node_instance')
@click.option('-v', '--verbose', is_flag=True)
def check(node_instance, verbose):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    rest_client = get_rest_client()
    ni = rest_client.node_instances.get(node_instance)
    agent = ni.runtime_properties['cloudify_agent']
    _output_agent(agent)

if __name__ == '__main__':
    main()
