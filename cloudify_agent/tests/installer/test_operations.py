import itertools
import logging

from mock import patch, ANY, call, Mock
import pytest

from cloudify.context import CloudifyContext
from cloudify.exceptions import NonRecoverableError
from cloudify.models_states import AgentState
from cloudify.state import current_ctx
from cloudify.workflows import local
from cloudify.utils import setup_logger
from cloudify.tests.mocks.mock_rest_client import MockRestclient

from cloudify_agent.api import utils
from cloudify_agent.installer.operations import start as start_operation
from cloudify_agent.tests import resources
from cloudify_agent.tests.utils import (
    get_source_uri,
    get_requirements_uri)
from cloudify_agent.tests import get_agent_dict
from cloudify_agent.tests.daemon import wait_for_daemon_dead
from cloudify_agent.tests.installer.config import get_tenant_mock
from cloudify_rest_client.manager import ManagerItem


logger = setup_logger(
    'cloudify-agent.tests.installer.test_operations',
    logger_level=logging.DEBUG)


##############################################################################
# these tests run a local workflow to install the agent on the local machine.
# it should support both windows and linux machines. and thus, testing the
# LocalWindowsAgentInstaller and LocalLinuxAgentInstaller.
# the remote use cases are tested as system tests because they require
# actually launching VMs from the test.
##############################################################################

@pytest.mark.only_posix
@pytest.mark.only_ci
def test_local_agent_from_package_posix(file_server, tmp_path,
                                        agent_ssl_cert, request):
    # Check that agent still works with a filepath longer than 128 bytes
    # (paths longer than 128 bytes break shebangs on linux.)
    agent_name = 'agent-{0}'.format(''.join('a' for _ in range(128)))
    _test_local_agent_from_package(agent_name, file_server, agent_ssl_cert,
                                   request)


@pytest.mark.only_nt
@pytest.mark.only_ci
def test_local_agent_from_package_nt(file_server, tmp_path, agent_ssl_cert,
                                     request):
    agent_name = utils.internal.generate_agent_name()
    _test_local_agent_from_package(agent_name, file_server, agent_ssl_cert,
                                   request)


@patch('cloudify.workflows.local._validate_node')
@patch('cloudify_agent.installer.operations.delete_agent_rabbitmq_user')
@patch('cloudify.agent_utils.get_rest_client',
       return_value=MockRestclient())
@get_tenant_mock()
@patch('cloudify.utils.get_manager_name', return_value='cloudify')
def _test_local_agent_from_package(agent_name, fs, ssl_cert, request, *_):

    agent_queue = '{0}-queue'.format(agent_name)

    blueprint_path = resources.get_resource(
        'blueprints/agent-from-package/local-agent-blueprint.yaml')
    logger.info('Initiating local env')

    inputs = {
        'resource_base': fs.root_path,
        'source_url': get_source_uri(),
        'requirements_file': get_requirements_uri(),
        'name': agent_name,
        'queue': agent_queue,
        'file_server_port': fs.port,
        'ssl_cert_path': ssl_cert.local_cert_path()
    }
    managers = [
        ManagerItem({
            'networks': {'default': '127.0.0.1'},
            'ca_cert_content': ssl_cert.DUMMY_CERT,
            'hostname': 'cloudify'
        })
    ]

    with patch('cloudify.endpoint.LocalEndpoint.get_managers',
               return_value=managers), \
        patch('cloudify.rabbitmq_client.RabbitMQClient.get_users',
              return_value=[]):
        env = local.init_env(name=request.node.name,
                             blueprint_path=blueprint_path,
                             inputs=inputs)

        env.execute('install', task_retries=0)
    agent_dict = get_agent_dict(env)
    ssl_cert.verify_remote_cert(agent_dict['agent_dir'])

    env.execute('uninstall', task_retries=1)
    wait_for_daemon_dead(agent_queue)


@patch('cloudify_agent.installer.operations.update_agent_record')
@patch('cloudify_agent.installer.operations.get_client')
@patch('cloudify_agent.api.utils.is_agent_alive')
@patch('cloudify.manager.get_rest_client')
def test_start_operation(
    rest_client_mock,
    is_agent_alive_mock,
    get_amqp_client_mock,
    update_agent_record_mock,
):
    """Test the agent start operation.

    This operation is used in plugin/init_script agent installation, and
    is supposed to just wait until the agent has started. It will call
    is_agent_alive and sleep over and over, until the agent is alive.
    """
    ctx = CloudifyContext({'node_id': 'a'})
    ctx._logger = Mock()  # no need to spam the logs
    is_agent_alive_mock.side_effect = [False] * 10 + [True]

    # every time.time() call will advance the clock by 10 seconds
    with patch('time.sleep') as sleep_mock, \
            patch('time.time', side_effect=itertools.count(step=10)):

        with current_ctx.push(ctx):
            start_operation(agent_config={
                'name': 'agent',
                'queue': 'agent',
                'install_method': 'plugin',
                'windows': False,
            })

    assert len(sleep_mock.mock_calls) == 10

    update_agent_record_mock.assert_has_calls([
        call(ANY, AgentState.STARTING),
        call(ANY, AgentState.STARTED),
    ])


@patch('cloudify_agent.installer.operations.update_agent_record')
@patch('cloudify_agent.installer.operations.get_client')
@patch('cloudify_agent.api.utils.is_agent_alive')
@patch('cloudify.manager.get_rest_client')
def test_start_operation_nonresponsive(
    rest_client_mock,
    is_agent_alive_mock,
    get_amqp_client_mock,
    update_agent_record_mock,
):
    """Like test_start_operation, but the agent takes a long time

    The difference is, the agent is also going to be marked nonresponsive.
    This is because is_agent_alive will report False for 50 tries
    (=500 seconds) and only then True
    """
    ctx = CloudifyContext({'node_id': 'a'})
    ctx._logger = Mock()
    is_agent_alive_mock.side_effect = [False] * 50 + [True]

    with patch('time.sleep') as sleep_mock, \
            patch('time.time', side_effect=itertools.count(step=10)):

        with current_ctx.push(ctx):
            start_operation(agent_config={
                'name': 'agent',
                'queue': 'agent',
                'install_method': 'plugin',
                'windows': False,
            })

    assert len(sleep_mock.mock_calls) == 50

    update_agent_record_mock.assert_has_calls([
        call(ANY, AgentState.STARTING),
        call(ANY, AgentState.NONRESPONSIVE),
        call(ANY, AgentState.STARTED),
    ])


@patch('cloudify_agent.installer.operations.update_agent_record')
@patch('cloudify_agent.installer.operations.get_client')
@patch('cloudify_agent.api.utils.is_agent_alive')
@patch('cloudify.manager.get_rest_client')
def test_start_operation_dead(
    rest_client_mock,
    is_agent_alive_mock,
    get_amqp_client_mock,
    update_agent_record_mock,
):
    """Like test_start_operation, but the agent never comes up

    We will keep trying for an hour (360 calls to is_agent_alive, because
    the mock time.time advances time by 10 seconds), and then throw
    NonRecoverableError.
    """
    ctx = CloudifyContext({'node_id': 'a'})
    ctx._logger = Mock()

    is_agent_alive_mock.return_value = False
    with patch('time.sleep'), \
            patch('time.time', side_effect=itertools.count(step=10)):

        with pytest.raises(NonRecoverableError):
            with current_ctx.push(ctx):
                start_operation(agent_config={
                    'name': 'agent',
                    'queue': 'agent',
                    'install_method': 'plugin',
                    'windows': False,
                })

    assert len(is_agent_alive_mock.mock_calls) == 360
