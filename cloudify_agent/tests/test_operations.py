import os
import platform
import shutil
from contextlib import contextmanager

from mock import patch, MagicMock
import pytest

from cloudify import constants
from cloudify import ctx
from cloudify import mocks
from cloudify.state import current_ctx
from cloudify.workflows import local
from cloudify.amqp_client import get_client
from cloudify.tests.mocks.mock_rest_client import MockRestclient
from cloudify_rest_client.manager import ManagerItem

from cloudify_agent import operations
from cloudify_agent.api import utils
from cloudify_agent.installer.config.agent_config import CloudifyAgentConfig
from cloudify_agent.tests import get_agent_dict
from cloudify_agent.tests import resources
from cloudify_agent.tests.daemon import (
    assert_daemon_alive,
    wait_for_daemon_dead,
)
from cloudify_agent.tests.installer.config import (
    mock_context,
    get_tenant_mock
)


@patch('cloudify_agent.installer.operations.delete_agent_rabbitmq_user')
@patch('cloudify.agent_utils.get_rest_client',
       return_value=MockRestclient())
@pytest.mark.only_ci
def test_install_new_agent(file_server, tmp_path, agent_ssl_cert, request,
                           agent_package, *_):
    agent_name = utils.internal.generate_agent_name()

    blueprint_path = resources.get_resource(
        'blueprints/install-new-agent/install-new-agent-blueprint.yaml')
    inputs = {
        'name': agent_name,
        'ssl_cert_path': agent_ssl_cert.get_local_cert_path()
    }

    with _manager_env(file_server, tmp_path, agent_ssl_cert, agent_package):
        env = local.init_env(name=request.node.name,
                             blueprint_path=blueprint_path,
                             inputs=inputs)
        env.execute('install', task_retries=0)
        agent_dict = get_agent_dict(env, 'new_agent_host')
        agent_ssl_cert.verify_remote_cert(agent_dict['agent_dir'])
        new_agent_name = agent_dict['name']
        assert new_agent_name != agent_name
        assert_daemon_alive(new_agent_name)
        env.execute('uninstall', task_retries=1)
        wait_for_daemon_dead(name=agent_name)
        wait_for_daemon_dead(name=new_agent_name)


@pytest.mark.only_posix
def test_create_agent_dict(agent_ssl_cert, tmp_path):
    with _set_context(agent_ssl_cert, tmp_path, host='192.0.2.98'):
        old_agent = _create_agent(agent_ssl_cert)
        new_agent = operations.create_new_agent_config(old_agent)
        new_agent['version'] = '3.4'
        third_agent = operations.create_new_agent_config(new_agent)
        equal_keys = ['ip', 'basedir', 'user']
        for k in equal_keys:
            assert old_agent[k] == new_agent[k]
            assert old_agent[k] == third_agent[k]
        nonequal_keys = ['agent_dir', 'workdir', 'envdir', 'name',
                         'rest_host']
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
@patch('cloudify_agent.operations._send_amqp_task')
@patch('cloudify_agent.api.utils.is_agent_alive',
       MagicMock(return_value=True))
@patch('cloudify.agent_utils.get_rest_client',
       return_value=MockRestclient())
def test_create_agent_from_old_agent(agent_ssl_cert, tmp_path, *mocks):
    with _set_context(agent_ssl_cert, tmp_path):
        _create_cloudify_agent_dir(tmp_path)
        old_name = ctx.instance.runtime_properties[
            'cloudify_agent']['name']
        old_agent_dir = ctx.instance.runtime_properties[
            'cloudify_agent']['agent_dir']
        old_queue = ctx.instance.runtime_properties[
            'cloudify_agent']['queue']

        operations.create_agent_amqp()
        new_name = ctx.instance.runtime_properties[
            'cloudify_agent']['name']
        new_agent_dir = ctx.instance.runtime_properties[
            'cloudify_agent']['agent_dir']
        new_queue = ctx.instance.runtime_properties[
            'cloudify_agent']['queue']
        assert old_name != new_name
        assert old_agent_dir != new_agent_dir
        assert old_queue != new_queue


rest_mock = MagicMock()
rest_mock.manager = MagicMock()
rest_mock.manager.get_version = lambda: '3.3'


def _create_agent(agent_ssl_cert):
    mock_ctx = mock_context(agent_ssl_cert)
    with (patch('cloudify_agent.installer.config.agent_config.ctx', mock_ctx),
          patch('cloudify.utils.ctx', mock_ctx)):
        old_agent = CloudifyAgentConfig({
            'install_method': 'remote',
            'ip': '10.0.4.47',
            'rest_host': '10.0.4.46',
            'distro': 'ubuntu',
            'distro_codename': 'trusty',
            'basedir': '/home/vagrant',
            'user': 'vagrant',
            'key': '~/.ssh/id_rsa',
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
def _set_context(agent_ssl_cert, tmp_path, host='localhost'):
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
    agent_script_dir = os.path.join(tmp_path, 'cloudify_agent')
    os.makedirs(agent_script_dir)


@contextmanager
def _manager_env(fileserver, tmp_path, ssl_cert, agent_package):
    port = 8756
    if os.name == 'nt':
        package_name = 'cloudify-windows-agent.exe'
    else:
        dist = platform.dist()
        package_name = '{0}-{1}-agent.tar.gz'.format(dist[0].lower(),
                                                     dist[2].lower())
    resources_dir = os.path.join(tmp_path, 'resources')
    agent_dir = os.path.join(resources_dir, 'packages', 'agents')
    agent_script_dir = os.path.join(resources_dir, 'cloudify_agent')
    os.makedirs(agent_dir)
    os.makedirs(agent_script_dir)
    os.makedirs(os.path.join(tmp_path, 'cloudify'))

    agent_path = os.path.join(agent_dir, package_name)
    shutil.copyfile(agent_package.get_package_path(), agent_path)

    new_env = {
        constants.MANAGER_FILE_SERVER_ROOT_KEY: resources_dir,
        constants.REST_PORT_KEY: str(port),
        constants.MANAGER_NAME: 'cloudify'
    }

    original_create_op_context = operations._get_cloudify_context

    def mock_create_op_context(agent,
                               task_name,
                               new_agent_connection=None):
        context = original_create_op_context(
            agent,
            task_name,
            new_agent_connection=new_agent_connection
        )
        context['__cloudify_context']['local'] = True
        return context

    # Need to patch, to avoid broker_ssl_enabled being True
    @contextmanager
    def get_amqp_client(agent):
        yield get_client()

    managers = [
        ManagerItem({
            'networks': {'default': '127.0.0.1'},
            'ca_cert_content': ssl_cert.DUMMY_CERT,
            'hostname': 'cloudify'
        })
    ]
    patches = [
        patch.dict(os.environ, new_env),
        patch('cloudify_agent.operations._get_amqp_client',
              get_amqp_client),
        patch('cloudify.endpoint.LocalEndpoint.get_managers',
              return_value=managers),
        patch('cloudify_agent.operations._get_cloudify_context',
              mock_create_op_context),
        get_tenant_mock()
    ]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()
