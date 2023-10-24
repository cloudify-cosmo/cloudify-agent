import json
import logging
import pkgutil

import click

from unittest import mock

from cloudify_agent.tests.shell.commands import run_agent_command


def test_debug_command_line():
    @click.command()
    def log():
        pass

    from cloudify_agent.shell.main import main
    main.add_command(log, 'log')
    run_agent_command('cfy-agent --debug log')

    # assert all loggers are now at debug level
    from cloudify_agent.api.utils import logger
    assert logger.level == logging.DEBUG


def test_version():
    mock_logger = mock.Mock()
    with mock.patch('cloudify_agent.shell.main.get_logger',
                    return_value=mock_logger):
        run_agent_command('cfy-agent --version')
    assert 1 == len(mock_logger.mock_calls)
    version = json.loads(
        pkgutil.get_data('cloudify_agent', 'VERSION'))['version']
    log_args = mock_logger.mock_calls[0][1]
    logged_output = log_args[0]
    assert version in logged_output
