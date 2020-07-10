import logging
import time

from cloudify.amqp_client import get_client
from cloudify.utils import setup_logger

from cloudify_agent.api import utils as agent_utils


logger = setup_logger(
    'cloudify-agent.tests.daemon',
    logger_level=logging.DEBUG)


def _is_agent_alive(name, timeout=10):
    return agent_utils.is_agent_alive(
        name,
        get_client(),
        timeout=timeout)


def assert_daemon_alive(name):
    assert _is_agent_alive(name)


def assert_daemon_dead(name):
    assert not _is_agent_alive(name)


def wait_for_daemon_alive(name, timeout=10):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if _is_agent_alive(name, timeout=5):
            return
        logger.info('Waiting for daemon {0} to start...'
                    .format(name))
        time.sleep(1)
    raise RuntimeError('Failed waiting for daemon {0} to start. Waited '
                       'for {1} seconds'.format(name, timeout))


def wait_for_daemon_dead(name, timeout=10):
    deadline = time.time() + timeout

    while time.time() < deadline:
        if not _is_agent_alive(name, timeout=5):
            return
        logger.info('Waiting for daemon {0} to stop...'
                    .format(name))
        time.sleep(1)
    raise RuntimeError('Failed waiting for daemon {0} to stop. Waited '
                       'for {1} seconds'.format(name, timeout))
