import os

import pytest

from cloudify_agent.tests.daemon import (
    wait_for_daemon_alive,
    wait_for_daemon_dead,
)
from cloudify_agent.tests.api.pm import shared


@pytest.mark.only_posix
def test_configure(detach_daemon):
    daemon = detach_daemon.create_daemon()
    daemon.create()

    daemon.configure()
    assert os.path.exists(daemon.script_path)
    assert os.path.exists(daemon.config_path)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_delete(detach_daemon):
    daemon = detach_daemon.create_daemon()
    daemon.create()
    daemon.configure()
    daemon.start()
    daemon.stop()
    daemon.delete()
    assert not os.path.exists(daemon.script_path)
    assert not os.path.exists(daemon.config_path)
    assert not os.path.exists(daemon.pid_file)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_cron_respawn(detach_daemon):
    daemon = detach_daemon.create_daemon(cron_respawn=True,
                                         cron_respawn_delay=1)
    daemon.create()
    daemon.configure()
    daemon.start()

    crontab = detach_daemon.runner.run('crontab -l').std_out
    assert daemon.cron_respawn_path in crontab

    wait_for_daemon_alive(daemon.queue)

    # lets kill the process
    detach_daemon.runner.run("pkill -9 -f 'cloudify_agent.worker'")
    wait_for_daemon_dead(daemon.queue)

    # check it was respawned
    # mocking cron - respawn it using the cron respawn script
    detach_daemon.runner.run(daemon.cron_respawn_path)
    wait_for_daemon_alive(daemon.queue)

    daemon.stop()
    wait_for_daemon_dead(daemon.queue)

    crontab = detach_daemon.runner.run('crontab -l').std_out
    assert daemon.cron_respawn_path not in crontab


@pytest.mark.only_posix
def test_create(detach_daemon):
    shared._test_create(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_create_overwrite(detach_daemon):
    shared._test_create_overwrite(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_start(detach_daemon):
    shared._test_start(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_start_delete_amqp_queue(detach_daemon):
    shared._test_start_delete_amqp_queue(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_start_with_error(detach_daemon):
    shared._test_start_with_error(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_start_short_timeout(detach_daemon):
    shared._test_start_short_timeout(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_status(detach_daemon):
    shared._test_status(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_stop(detach_daemon):
    shared._test_stop(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_stop_short_timeout(detach_daemon):
    shared._test_stop_short_timeout(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_restart(detach_daemon):
    shared._test_restart(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_two_daemons(detach_daemon):
    shared._test_two_daemons(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_conf_env_variables(detach_daemon):
    shared._test_conf_env_variables(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_extra_env(detach_daemon):
    shared._test_extra_env(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_execution_env(detach_daemon):
    shared._test_execution_env(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_delete_before_stop(detach_daemon):
    shared._test_delete(detach_daemon)


@pytest.mark.only_rabbit
@pytest.mark.only_posix
def test_logging(detach_daemon):
    shared._test_logging(detach_daemon)
