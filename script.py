#!/opt/mgmtworker/env/bin/python

import click
import logging
import itertools

from cloudify_cli.env import get_rest_client, profile
from cloudify_agent.operations import _celery_app

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


@click.command()
@click.option('-v', '--verbose', is_flag=True)
@click.option('--all-tenants/--no-all-tenants', is_flag=True, default=True,
              help='Update node instances of all tenants')
@click.option('--dry-run', is_flag=True, help="Don't actually update anything")
def main(verbose, all_tenants, dry_run):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    rest_client = get_rest_client()
    _check_status(rest_client)
    node_instances = _get_node_instances(rest_client, all_tenants)
    agent_instances = itertools.ifilter(is_agent_instance, node_instances)

    for agent in agent_instances:
        with _celery_app(agent.runtime_properties['cloudify_agent']) as c:
            print c


if __name__ == '__main__':
    main()
