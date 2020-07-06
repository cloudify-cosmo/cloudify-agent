import os
import uuid
import shutil

from mock import patch

from cloudify import ctx
from cloudify.utils import LocalCommandRunner
from cloudify.state import current_ctx
from cloudify.tests.mocks.mock_rest_client import MockRestclient
from cloudify_agent.tests import agent_ssl_cert
from cloudify_agent.tests.api.pm import only_ci
from cloudify_agent.tests.daemon import (
    assert_daemon_dead,
    wait_for_daemon_alive,
)
from cloudify_agent.installer.config.agent_config import CloudifyAgentConfig
from cloudify_agent.installer.operations import create as create_agent
from cloudify_agent.tests.installer.config import mock_context


@patch('cloudify.agent_utils.get_rest_client',
       return_value=MockRestclient())
@patch('cloudify.utils.get_manager_name', return_value='cloudify')
def _test_agent_installation(agent_config):
    new_ctx = mock_context()
    current_ctx.set(new_ctx)

    assert_daemon_dead(agent_config['name'])
    create_agent(agent_config=agent_config)
    wait_for_daemon_alive(agent_config['name'])

    new_agent = ctx.instance.runtime_properties['cloudify_agent']

    agent_ssl_cert.verify_remote_cert(new_agent['agent_dir'])

    command_format = 'cfy-agent daemons {0} --name {1}'.format(
        '{0}',
        new_agent['name'])
    runner = LocalCommandRunner()
    runner.run(command_format.format('stop'))
    runner.run(command_format.format('delete'))

    assert_daemon_dead(agent_config['name'])
    return new_agent


def _get_agent_config(agent_package, agent_ssl_cert):
    return CloudifyAgentConfig({
        'name': '{0}_{1}'.format('agent_', str(uuid.uuid4())),
        'ip': 'localhost',
        'package_url': agent_package.get_package_url(),
        'rest_host': 'localhost',
        'broker_ip': 'localhost',
        'windows': os.name == 'nt',
        'local': True,
        'ssl_cert_path': agent_ssl_cert.get_local_cert_path()
    })


@only_ci
def test_installation(agent_package, tmpdir_factory, agent_ssl_cert):
    base_dir = tmpdir_factory.mktemp()
    agent_config = _get_agent_config(agent_package, agent_ssl_cert)
    agent_config['basedir'] = base_dir
    try:
        _test_agent_installation(agent_config)
    finally:
        shutil.rmtree(base_dir)


@only_ci
def test_installation_no_basedir(agent_package, agent_ssl_cert):
    agent_config = _get_agent_config(agent_package, agent_ssl_cert)
    new_agent = _test_agent_installation(agent_config)
    assert 'basedir' in new_agent
