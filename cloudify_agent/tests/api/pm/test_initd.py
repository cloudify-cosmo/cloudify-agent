import os

import pytest

from cloudify_agent.tests.daemon import (
    wait_for_daemon_alive,
    wait_for_daemon_dead,
)
from cloudify_agent.tests.api.pm import shared


SCRIPT_DIR = '/tmp/etc/init.d'
CONFIG_DIR = '/tmp/etc/default'


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_configure(initd_daemon):
    daemon = initd_daemon.create_daemon()
    daemon.create()

    daemon.configure()
    assert os.path.exists(daemon.script_path)
    assert os.path.exists(daemon.config_path)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_delete(initd_daemon):
    daemon = initd_daemon.create_daemon()
    daemon.create()
    daemon.configure()
    daemon.start()
    daemon.stop()
    daemon.delete()
    assert not os.path.exists(daemon.script_path)
    assert not os.path.exists(daemon.config_path)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_configure_start_on_boot(initd_daemon):
    daemon = initd_daemon.create_daemon(start_on_boot=True)
    daemon.create()
    daemon.configure()


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_cron_respawn(initd_daemon):
    daemon = initd_daemon.create_daemon(cron_respawn=True,
                                        cron_respawn_delay=1)
    daemon.create()
    daemon.configure()
    daemon.start()

    # initd daemon's cron is for root, so that respawning the daemon can
    # use the init system which requires root
    crontab = initd_daemon.runner.run('sudo crontab -lu root').std_out
    assert daemon.cron_respawn_path in crontab

    initd_daemon.runner.run("pkill -9 -f 'cloudify_agent.worker'")
    wait_for_daemon_dead(daemon.queue)

    # check it was respawned
    # mocking cron - respawn it using the cron respawn script
    initd_daemon.runner.run(daemon.cron_respawn_path)
    wait_for_daemon_alive(daemon.queue)

    # this should also disable the crontab entry
    daemon.stop()
    wait_for_daemon_dead(daemon.queue)

    crontab = initd_daemon.runner.run('sudo crontab -lu root').std_out
    assert daemon.cron_respawn_path not in crontab


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_create(initd_daemon):
    shared._test_create(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_create_overwrite(initd_daemon):
    shared._test_create_overwrite(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_start(initd_daemon):
    shared.test_start(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_start_delete_amqp_queue(initd_daemon):
    shared.test_start_delete_amqp_queue(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_start_with_error(initd_daemon):
    shared.test_start_with_error(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_start_short_timeout(initd_daemon):
    shared.test_start_short_timeout(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_status(initd_daemon):
    shared.test_status(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_stop(initd_daemon):
    shared.test_stop(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_stop_short_timeout(initd_daemon):
    shared.test_stop_short_timeout(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_restart(initd_daemon):
    shared.test_restart(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_two_daemons(initd_daemon):
    shared.test_two_daemons(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_conf_env_variables(initd_daemon):
    shared.test_conf_env_Variables(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_extra_env(initd_daemon):
    shared.test_extra_env(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_execution_env(initd_daemon):
    shared.test_execution_env(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_delete_before_stop(initd_daemon):
    shared.test_delete_before_stop(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_delete_before_stop_with_force(initd_daemon):
    shared.test_delete_before_stop_with_force(initd_daemon)


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_logging(initd_daemon):
    shared.test_logging(initd_daemon)
