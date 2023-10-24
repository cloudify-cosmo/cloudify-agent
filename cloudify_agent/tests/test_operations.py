import os
import pytest

from contextlib import contextmanager

from unittest.mock import patch, MagicMock

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from cloudify import constants
from cloudify import ctx
from cloudify import mocks
from cloudify.state import current_ctx

from cloudify_agent import operations
from cloudify_agent.installer.config.agent_config import CloudifyAgentConfig
from cloudify_agent.tests.installer.config import mock_context


@pytest.mark.only_posix
def test_create_agent_dict(agent_ssl_cert, tmp_path):
    with _set_context(agent_ssl_cert, tmp_path, host='192.0.2.98'):
        old_agent = _create_agent(agent_ssl_cert)
        new_agent = operations.create_new_agent_config(old_agent)
        new_agent['version'] = '3.4'
        third_agent = operations.create_new_agent_config(new_agent)
        equal_keys = ['ip', 'user']
        for k in equal_keys:
            assert old_agent[k] == new_agent[k]
            assert old_agent[k] == third_agent[k]
        nonequal_keys = ['name', 'rest_host']
        for k in nonequal_keys:
            assert old_agent[k] != new_agent[k]
            assert old_agent[k] != third_agent[k]
        old_name = old_agent['name']
        new_name = new_agent['name']
        third_name = third_agent['name']
        assert old_name in new_name
        assert old_name in third_name
        assert len(third_name) <= len(new_name)
        new_agent['name'] = '{0}{1}'.format(new_agent['name'], 'not-uuid')
        agent = operations.create_new_agent_config(new_agent)
        assert new_agent['name'] in agent['name']


@pytest.mark.only_posix
def test_create_agent_from_old_agent(mock_get_rest_client, tmp_path,
                                     mock_send_amqp_task,
                                     mock_is_agent_alive, agent_ssl_cert):
    get_rmq_user_path = (
        'cloudify_agent.installer.config.agent_config.get_agent_rabbitmq_user'
    )
    with _set_context(agent_ssl_cert, tmp_path), patch(get_rmq_user_path):
        _create_cloudify_agent_dir(tmp_path)
        old_name = ctx.instance.runtime_properties[
            'cloudify_agent']['name']
        old_queue = ctx.instance.runtime_properties[
            'cloudify_agent']['queue']

        operations.create_agent_amqp()
        new_name = ctx.instance.runtime_properties[
            'cloudify_agent']['name']
        new_queue = ctx.instance.runtime_properties[
            'cloudify_agent']['queue']
        assert old_name != new_name
        assert old_queue != new_queue


rest_mock = MagicMock()
rest_mock.manager = MagicMock()
rest_mock.manager.get_version = lambda: '3.3'


def _create_agent(agent_ssl_cert):
    mock_ctx = mock_context(agent_ssl_cert)
    with patch('cloudify_agent.installer.config.agent_config.ctx',
               mock_ctx), patch('cloudify.utils.ctx', mock_ctx):
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        private_key = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode('utf-8')

        old_agent = CloudifyAgentConfig({
            'install_method': 'remote',
            'ip': '10.0.4.47',
            'rest_host': '10.0.4.46',
            'architecture': 'x86_64',
            'basedir': '/home/vagrant',
            'user': 'vagrant',
            'key': private_key,
            'windows': False,
            'package_url': 'http://10.0.4.46:53229/packages/agents/'
                           'ubuntu-trusty-agent.tar.gz',
            'version': '4.4',
            'broker_config': {
                'broker_ip': '10.0.4.46',
                'broker_pass': 'test_pass',
                'broker_user': 'test_user',
                'broker_ssl_cert': ''
            }
        })

        old_agent.set_execution_params()
        old_agent.set_default_values()
        old_agent.set_installation_params(runner=None)
        return old_agent


@contextmanager
def _set_context(agent_ssl_cert, tmp_path, host='127.0.0.1'):
    old_context = ctx
    try:
        os.environ[constants.MANAGER_FILE_SERVER_ROOT_KEY] = \
            str(tmp_path)
        os.environ[constants.MANAGER_NAME] = 'cloudify'
        properties = {}
        properties['cloudify_agent'] = _create_agent(agent_ssl_cert)
        properties['agent_status'] = {'agent_alive_crossbroker': True}
        mock = mocks.MockCloudifyContext(
            node_id='host_af231',
            runtime_properties=properties,
            node_name='host',
            properties={'cloudify_agent': {}},
            brokers=[{
                'networks': {'default': host}
            }],
            managers=[{
                'networks': {'default': host},
                'hostname': 'cloudify'
            }]
        )
        current_ctx.set(mock)
        yield
    finally:
        current_ctx.set(old_context)


def _create_cloudify_agent_dir(tmp_path):
    agent_script_dir = os.path.join(str(tmp_path), 'cloudify_agent')
    os.makedirs(agent_script_dir)
