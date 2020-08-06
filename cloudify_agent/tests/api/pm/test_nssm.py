import os
import time

import pytest

from cloudify.exceptions import CommandExecutionException

from cloudify_agent.tests.api.pm import shared


@pytest.mark.only_nt
def test_configure(nssm_daemon):
    daemon = nssm_daemon.create_daemon()
    daemon.create()
    daemon.configure()
    assert os.path.exists(daemon.config_path)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_delete(nssm_daemon):
    daemon = nssm_daemon.create_daemon()
    daemon.create()
    daemon.configure()
    daemon.start()
    daemon.stop()
    daemon.delete()
    assert not os.path.exists(daemon.config_path)
    pytest.raises(
        CommandExecutionException,
        nssm_daemon.runner.run,
        'sc getdisplayname {0}'.format(daemon.name))


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_status(nssm_daemon):
    daemon = nssm_daemon.create_daemon()
    daemon.create()
    daemon.configure()
    assert not daemon.status()
    daemon.start()
    # on windows, the daemon.start completes and returns fast enough
    # that the service state is still SERVICE_START_PENDING
    for retry in range(5):
        if daemon.status():
            break
        time.sleep(1)
    else:
        pytest.fail('Daemon failed to start')


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_create(nssm_daemon):
    shared._test_create(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_create_overwrite(nssm_daemon):
    shared._test_create_overwrite(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_start(nssm_daemon):
    shared._test_start(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_start_delete_amqp_queue(nssm_daemon):
    shared._test_start_delete_amqp_queue(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_start_short_timeout(nssm_daemon):
    shared._test_start_short_timeout(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_stop(nssm_daemon):
    shared._test_stop(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_restart(nssm_daemon):
    shared._test_restart(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_two_daemons(nssm_daemon):
    shared._test_two_daemons(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_conf_env_variables(nssm_daemon):
    shared._test_conf_env_variables(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_extra_env(nssm_daemon):
    shared._test_extra_env(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_execution_env(nssm_daemon):
    shared._test_execution_env(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_delete_before_stop(nssm_daemon):
    shared._test_delete_before_stop(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_delete_before_stop_with_force(nssm_daemon):
    shared._test_delete_before_stop_with_force(nssm_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_nt
def test_logging(nssm_daemon):
    shared._test_logging(nssm_daemon)
