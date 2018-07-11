#!/opt/cfy/embedded/bin/python
"""
A script to update agent node instances with the given certificate.

This script uses the REST client to do the update, therefore it needs to
be run from a virtualenv with the REST client installed. It will also use
the CLI profile, so it must be run as a user with a CLI profile defined.

To use this, either:
  - upload this script to the manager, chmod +x it, and run it; or
  - run it using `python script.py ...` from another machine, from a CLI
    virtualenv

USING DRY-RUN FIRST IS RECOMMENDED (--dry-run)

Either pass `--cert path/to/cert.pem` to update agent node instances with
the new cert, or omit that flag, to make this script remove the cert from
the node instances, which will cause the manager to use the cert configured
in the mgmtworker, which should also be correct.

When changing the cert preexisting in the node instances, to the provide one,
this script will copy the old cert to a separate runtime property. You can
then use `--revert` to undo this work and go to the previous cert, if
necessary.
"""


import itertools
import click
import logging
from cloudify_cli.env import get_rest_client, profile

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


def _revert_broker_config(agent):
    agent['broker_config']['broker_ssl_cert'] = \
        agent.pop('old_broker_ssl_cert', None)


def _change_broker_config(agent, cert):
    broker_config = agent['broker_config']
    old_cert = broker_config.get('broker_ssl_cert')
    if cert:
        broker_config['broker_ssl_cert'] = cert
    else:
        del broker_config['broker_ssl_cert']
    agent['old_broker_ssl_cert'] = old_cert


def _validate_node_instance(node_instance):
    try:
        node_instance.runtime_properties['cloudify_agent']['broker_config']
    except KeyError:
        logging.warning('No cloudify_agent.broker_config in %s',
                        node_instance.id)
        return False
    return True


def _update_node_instance(rest_client, node_instance, cert, dry_run=False,
                          revert=False):
    logging.info('Updating agent node instance %s', node_instance.id)
    runtime_properties = node_instance.runtime_properties
    try:
        agent = runtime_properties['cloudify_agent']
        broker_config = agent['broker_config']
    except KeyError:
        logging.warning('No cloudify_agent.broker_config in %s',
                        node_instance.id)
        return

    if revert:
        logging.info('%s: reverting cert', node_instance.id)
        _revert_broker_config(agent)
    else:
        logging.info('%s: updating cert', node_instance.id)
        _change_broker_config(agent, cert)

    logging.info('%s: saving%s', node_instance.id,
                 ' (dry-run: True, not actually saving)' if dry_run else '')
    if not dry_run:
        rest_client.node_instances.update(
            node_instance.id,
            runtime_properties=runtime_properties,
            version=node_instance.version)
    logging.debug('%s broker_config: %s', node_instance.id, broker_config)


def load_cert(ctx, param, value):
    if not value:
        return
    with open(value) as f:
        cert = f.read()
    if '---BEGIN CERTIFICATE---' not in cert:
        raise ValueError('{0} is not a valid certificate file'.format(value))
    return cert


@click.command()
@click.option('-v', '--verbose', is_flag=True)
@click.option('--force', is_flag=True, help='Attempt to change even with '
                                            'failing validations')
@click.option('--all-tenants/--no-all-tenants', is_flag=True, default=True,
              help='Update node instances of all tenants')
@click.option('--dry-run', is_flag=True, help="Don't actually update anything")
@click.option('--revert', is_flag=True,
              help='Revert the work of this script, restoring previous '
                   'certificate in node instances')
@click.option('--cert', callback=load_cert,
              help='Certificate file to update the node instances with')
@click.option('--node-instance', multiple=True,
              help='Only work on those node instances')
def main(verbose, all_tenants, dry_run, cert, revert, force, node_instance):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    rest_client = get_rest_client()
    _check_status(rest_client)
    if node_instance:
        node_instances = [rest_client.node_instances.get(ni)
                          for ni in node_instance]
    else:
        node_instances = _get_node_instances(rest_client, all_tenants)
    agent_instances = itertools.ifilter(is_agent_instance, node_instances)
    # clone the iterator so that we can validate all of them up front
    agents1, agents2 = itertools.tee(agent_instances)
    if not all(_validate_node_instance(ni) for ni in agents1) and not force:
        raise ValueError('Some node instances did not validate')
    for ni in agents2:
        _update_node_instance(rest_client, ni, cert, dry_run, revert)


if __name__ == '__main__':
    main()
