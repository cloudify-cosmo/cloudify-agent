import itertools
import logging

from mock import patch, ANY, call, Mock
import pytest

from cloudify.context import CloudifyContext
from cloudify.exceptions import NonRecoverableError
from cloudify.models_states import AgentState
from cloudify.state import current_ctx
from cloudify.utils import setup_logger

from cloudify_agent.installer.operations import start as start_operation


logger = setup_logger(
    'cloudify-agent.tests.installer.test_operations',
    logger_level=logging.DEBUG)


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
