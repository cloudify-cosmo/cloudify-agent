import logging
import sys

from cloudify_agent.shell import main as cli
from cloudify.utils import setup_logger


logger = setup_logger(
    'cloudify-agent.tests.shell.commands',
    logger_level=logging.DEBUG)


def run_agent_command(self, command, raise_system_exit=False):
    sys.argv = command.split()
    logger.info('Running cfy-agent command with '
                'sys.argv={0}'.format(sys.argv))
    try:
        cli.main()
    except SystemExit as e:
        if raise_system_exit and e.code != 0:
            raise
