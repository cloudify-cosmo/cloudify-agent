import os

from mock import patch
import pytest

from cloudify import ctx
from cloudify.utils import LocalCommandRunner
from cloudify.state import current_ctx
from cloudify.tests.mocks.mock_rest_client import MockRestclient
from cloudify_agent.tests.daemon import (
    assert_daemon_dead,
    wait_for_daemon_alive,
)
from cloudify_agent.installer.config.agent_config import CloudifyAgentConfig
from cloudify_agent.installer.operations import create as create_agent
from cloudify_agent.tests import random_id
from cloudify_agent.tests.installer.config import mock_context


@pytest.mark.only_ci
def test_installation(agent_package, tmpdir_factory, agent_ssl_cert):
    base_dir = tmpdir_factory.mktemp('install_base_dir')
    agent_config = _get_agent_config(agent_package, agent_ssl_cert)
    agent_config['basedir'] = str(base_dir)
    _test_agent_installation(agent_ssl_cert, agent_config)


@pytest.mark.only_ci
def test_installation_no_basedir(agent_package, agent_ssl_cert):
    agent_config = _get_agent_config(agent_package, agent_ssl_cert)
    new_agent = _test_agent_installation(agent_ssl_cert, agent_config)
    assert 'basedir' in new_agent


@patch('cloudify.agent_utils.get_rest_client',
       return_value=MockRestclient())
@patch('cloudify.agent_utils.get_agent_rabbitmq_user',
       return_value={})
@patch('cloudify.utils.get_manager_name', return_value='cloudify')
def _test_agent_installation(agent_ssl_cert, agent_config, *_):
    new_ctx = mock_context(agent_ssl_cert)
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
        'name': '{0}_{1}'.format('agent_', str(random_id(with_prefix=False))),
        'ip': '127.0.0.1',
        'package_url': agent_package.get_package_url(),
        'rest_host': '127.0.0.1',
        'broker_ip': '127.0.0.1',
        'windows': os.name == 'nt',
        'local': True,
        'ssl_cert_path': agent_ssl_cert.local_cert_path()
    })
