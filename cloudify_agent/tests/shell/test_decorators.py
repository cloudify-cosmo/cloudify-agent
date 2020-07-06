import click
import pytest

from cloudify_agent.api import exceptions
from cloudify_agent.shell.decorators import handle_failures

from cloudify_agent.tests.shell.commands import run_agent_command


def test_api_exceptions_conversion():
    @click.command()
    @handle_failures
    def _raise_api_exception():
        raise exceptions.DaemonException()

    from cloudify_agent.shell.main import main
    main.add_command(_raise_api_exception, 'raise-error')
    try:
        run_agent_command('cfy-agent raise-error', raise_system_exit=True)
        pytest.fail('Expected failure of command execution')
    except SystemExit as e:
        assert e.code == 101


def test_api_errors_conversion():
    @click.command()
    @handle_failures
    def _raise_api_error():
        raise exceptions.DaemonError()

    from cloudify_agent.shell.main import main
    main.add_command(_raise_api_error, 'raise-error')
    try:
        run_agent_command('cfy-agent raise-error', raise_system_exit=True)
        pytest.fail('Expected failure of command execution')
    except SystemExit as e:
        assert e.code == 201
