import os

from mock import patch
import pytest

from cloudify import constants

from cloudify_agent.api import exceptions
from cloudify_agent.api import utils
from cloudify_agent.api.plugins import installer
from cloudify_agent.tests.daemon import (
    assert_daemon_alive,
    wait_for_daemon_alive,
    wait_for_daemon_dead,
)
from cloudify_agent.tests.api.pm import DEPLOYMENT_ID


def patch_get_source():
    return patch('cloudify_agent.api.plugins.installer.get_plugin_source',
                 lambda plugin, blueprint_id: plugin.get('source'))


def patch_no_managed_plugin():
    return patch('cloudify_agent.api.plugins.installer.get_managed_plugin',
                 lambda plugin: None)


def _test_create(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()


def _test_create_overwrite(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    daemon.start()
    wait_for_daemon_alive(daemon.queue)

    daemon.create()
    daemon.configure()
    daemon.start()

    wait_for_daemon_alive(daemon.queue)
    daemon.stop()
    wait_for_daemon_dead(daemon.queue)


def _test_start(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    daemon.start()


def _test_start_delete_amqp_queue(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()

    # this creates the queue
    daemon.start()

    daemon.stop()
    daemon.start(delete_amqp_queue=True)


@patch_get_source()
def _test_start_with_error(daemon_fixture):
    if os.name == 'nt':
        log_dir = 'H:\\WATT_NONEXISTENT_DIR\\lo'
    else:
        log_dir = '/root/no_permission'
    daemon = daemon_fixture.create_daemon(log_dir=log_dir)
    daemon.create()
    daemon.configure()
    if os.name == 'nt':
        expected_error = '.*WATT_NONEXISTENT_DIR.*'
    else:
        expected_error = ".*Permission denied: '/root/no_permission.*"
    with pytest.raises(exceptions.DaemonError, match=expected_error):
        daemon.start(timeout=5)


def _test_start_short_timeout(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    with pytest.raises(exceptions.DaemonStartupTimeout,
                       match='.*failed to start in -1 seconds.*'):
        daemon.start(timeout=-1)


def _test_status(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    assert not daemon.status()
    daemon.start()
    assert daemon.status()


def _test_stop(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    daemon.start()
    daemon.stop()
    wait_for_daemon_dead(daemon.queue)


def _test_stop_short_timeout(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    daemon.start()
    with pytest.raises(exceptions.DaemonShutdownTimeout,
                       match='.*failed to stop in -1 seconds.*'):
        daemon.stop(timeout=-1)


@patch_get_source()
@patch_no_managed_plugin()
def _test_restart(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    installer.install(daemon_fixture.plugin_struct())
    daemon.start()
    daemon.restart()


def _test_two_daemons(daemon_fixture):
    daemon1 = daemon_fixture.create_daemon()
    daemon1.create()
    daemon1.configure()

    daemon1.start()
    assert_daemon_alive(daemon1.queue)

    daemon2 = daemon_fixture.create_daemon()
    daemon2.create()
    daemon2.configure()

    daemon2.start()
    assert_daemon_alive(daemon2.queue)


@patch_get_source()
@patch_no_managed_plugin()
def _test_conf_env_variables(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    installer.install(daemon_fixture.plugin_struct())
    daemon.start()

    expected = {
        constants.REST_HOST_KEY: ','.join(daemon.rest_host),
        constants.REST_PORT_KEY: str(daemon.rest_port),
        constants.MANAGER_FILE_SERVER_URL_KEY: ','.join(
            'https://{0}:{1}/resources'.format(host, daemon.rest_port)
            for host in daemon.rest_host),
        constants.AGENT_WORK_DIR_KEY: daemon.workdir,
    }

    def _get_env_var(var):
        return daemon_fixture.send_task(
            task_name='mock_plugin.tasks.get_env_variable',
            queue=daemon.queue,
            kwargs={'env_variable': var})

    def _check_env_var(var, expected_value):
        _value = _get_env_var(var)
        assert _value == expected_value

    for key, value in expected.items():
        _check_env_var(key, value)


@patch_get_source()
@patch_no_managed_plugin()
def _test_extra_env(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.extra_env_path = utils.env_to_file(
        {'TEST_ENV_KEY': 'TEST_ENV_VALUE'},
        posix=os.name == 'posix'
    )
    daemon.create()
    daemon.configure()
    installer.install(daemon_fixture.plugin_struct())
    daemon.start()

    # check the env file was properly sourced by querying the env
    # variable from the daemon process. this is done by a task
    value = daemon_fixture.send_task(
        task_name='mock_plugin.tasks.get_env_variable',
        queue=daemon.queue,
        kwargs={'env_variable': 'TEST_ENV_KEY'})
    assert value == 'TEST_ENV_VALUE'


@patch_get_source()
@patch_no_managed_plugin()
def _test_execution_env(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    installer.install(daemon_fixture.plugin_struct())
    daemon.start()

    # check that cloudify.dispatch.dispatch 'execution_env' processing
    # works.
    # not the most ideal place for this test. but on the other hand
    # all the boilerplate is already here, so this is too tempting.
    value = daemon_fixture.send_task(
        task_name='mock_plugin.tasks.get_env_variable',
        queue=daemon.queue,
        kwargs={'env_variable': 'TEST_ENV_KEY2'},
        execution_env={'TEST_ENV_KEY2': 'TEST_ENV_VALUE2'})
    assert value == 'TEST_ENV_VALUE2'


def _test_delete_before_stop(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    daemon.start()
    pytest.raises(exceptions.DaemonStillRunningException,
                  daemon.delete)


def _test_delete_before_stop_with_force(daemon_fixture):
    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    daemon.start()
    daemon.delete(force=True)
    wait_for_daemon_dead(daemon.queue)


@patch_get_source()
@patch_no_managed_plugin()
def _test_logging(daemon_fixture):
    message = 'THIS IS THE TEST MESSAGE LOG CONTENT'

    daemon = daemon_fixture.create_daemon()
    daemon.create()
    daemon.configure()
    installer.install(daemon_fixture.plugin_struct())
    installer.install(daemon_fixture.plugin_struct(),
                      deployment_id=DEPLOYMENT_ID)
    daemon.start()

    def log_and_assert(_message, _deployment_id=None):
        daemon_fixture.send_task(
            task_name='mock_plugin.tasks.do_logging',
            queue=daemon.queue,
            kwargs={'message': _message},
            deployment_id=_deployment_id)

        name = _deployment_id if _deployment_id else '__system__'
        logdir = os.path.join(daemon.workdir, 'logs')
        logfile = os.path.join(logdir, '{0}.log'.format(name))
        try:
            with open(logfile) as f:
                assert _message in f.read()
        except IOError:
            daemon_fixture.logger.warning('{0} content: {1}'.format(
                logdir, os.listdir(logdir)))
            raise

    # Test __system__ logs
    log_and_assert(message)
    # Test deployment logs
    log_and_assert(message, DEPLOYMENT_ID)
