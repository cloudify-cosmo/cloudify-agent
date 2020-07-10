import os

import cloudify_agent.shell.env as env_constants
from cloudify_agent.api import utils
from cloudify_agent.shell.main import get_logger
from cloudify_agent.tests.shell.commands import run_agent_command


def test_create(mock_daemon_factory_new,
                mock_daemon_factory_save,
                mock_daemon_factory_load,
                mock_daemon_factory_delete,
                mock_daemon_factory_load_all,
                mock_get_storage_dir):
    run_agent_command('cfy-agent daemons create --name=name '
                      '--process-management=init.d --user=user '
                      '--queue=queue  --rest-host=127.0.0.1')

    mock_daemon_factory_new.assert_called_once_with(
        name='name',
        queue='queue',
        user='user',
        rest_host=['127.0.0.1'],
        process_management='init.d',
        broker_ip=None,
        workdir=None,
        log_level=None,
        pid_file=None,
        log_dir=None,
        max_workers=None,
        min_workers=None,
        rest_port='80',
        host=None,
        deployment_id=None,
        extra_env_path=None,
        logger=get_logger(),
        broker_user='guest',
        broker_pass='guest',
        broker_vhost='/',
        broker_ssl_cert=None,
        broker_ssl_enabled=False,
        heartbeat=30,
        rest_username=None,
        rest_password=None,
        rest_token=None,
        rest_tenant=None,
        broker_ssl_cert_path=os.environ[
            env_constants.CLOUDIFY_BROKER_SSL_CERT_PATH],
        local_rest_cert_file=os.environ[
            env_constants.CLOUDIFY_LOCAL_REST_CERT_PATH],
        bypass_maintenance_mode=None,
        network=None,
        executable_temp_path=None,
        log_max_bytes=None,
        log_max_history=None
    )

    daemon = mock_daemon_factory_new.return_value
    daemon.create.assert_called_once_with()


def test_create_with_custom_options(mock_daemon_factory_new,
                                    mock_daemon_factory_save,
                                    mock_daemon_factory_load,
                                    mock_daemon_factory_delete,
                                    mock_daemon_factory_load_all,
                                    mock_get_storage_dir):
    run_agent_command('cfy-agent daemons create --name=name --queue=queue '
                      '--rest-host=127.0.0.1 --broker-ip=127.0.0.1 '
                      '--process-management=init.d --rest-tenant=tenant '
                      '--user=user --key=value --complex-key=complex-value')

    mock_daemon_factory_new.assert_called_once_with(
        name='name',
        queue='queue',
        user='user',
        rest_host=['127.0.0.1'],
        process_management='init.d',
        broker_ip=['127.0.0.1'],
        workdir=None,
        max_workers=None,
        min_workers=None,
        host=None,
        deployment_id=None,
        log_level=None,
        pid_file=None,
        log_dir=None,
        rest_port='80',
        extra_env_path=None,
        logger=get_logger(),
        key='value',
        complex_key='complex-value',
        broker_user='guest',
        broker_pass='guest',
        broker_vhost='/',
        broker_ssl_cert=None,
        broker_ssl_enabled=False,
        heartbeat=30,
        broker_ssl_cert_path=os.environ[
            env_constants.CLOUDIFY_BROKER_SSL_CERT_PATH],
        rest_username=None,
        rest_password=None,
        rest_token=None,
        rest_tenant='tenant',
        local_rest_cert_file=os.environ[
            env_constants.CLOUDIFY_LOCAL_REST_CERT_PATH],
        bypass_maintenance_mode=None,
        network=None,
        log_max_bytes=None,
        log_max_history=None,
        executable_temp_path=None
    )


def test_configure(mock_daemon_factory_new,
                   mock_daemon_factory_save,
                   mock_daemon_factory_load,
                   mock_daemon_factory_delete,
                   mock_daemon_factory_load_all,
                   mock_get_storage_dir):
    run_agent_command('cfy-agent daemons configure --name=name ')

    mock_daemon_factory_load.assert_called_once_with('name',
                                                     logger=get_logger())

    daemon = mock_daemon_factory_load.return_value
    daemon.configure.assert_called_once_with()

    mock_daemon_factory_save.assert_called_once_with(daemon)


def test_start(mock_daemon_factory_new,
               mock_daemon_factory_save,
               mock_daemon_factory_load,
               mock_daemon_factory_delete,
               mock_daemon_factory_load_all,
               mock_get_storage_dir):
    run_agent_command('cfy-agent daemons start --name=name '
                      '--interval 5 --timeout 20 --no-delete-amqp-queue')

    mock_daemon_factory_load.assert_called_once_with('name',
                                                     logger=get_logger())

    daemon = mock_daemon_factory_load.return_value
    daemon.start.assert_called_once_with(
        interval=5,
        timeout=20,
        delete_amqp_queue=True,
    )


def test_stop(mock_daemon_factory_new,
              mock_daemon_factory_save,
              mock_daemon_factory_load,
              mock_daemon_factory_delete,
              mock_daemon_factory_load_all,
              mock_get_storage_dir):
    run_agent_command('cfy-agent daemons stop --name=name '
                      '--interval 5 --timeout 20')

    mock_daemon_factory_load.assert_called_once_with('name',
                                                     logger=get_logger())

    daemon = mock_daemon_factory_load.return_value
    daemon.stop.assert_called_once_with(
        interval=5,
        timeout=20
    )


def test_delete(mock_daemon_factory_new,
                mock_daemon_factory_save,
                mock_daemon_factory_load,
                mock_daemon_factory_delete,
                mock_daemon_factory_load_all,
                mock_get_storage_dir):
    run_agent_command('cfy-agent daemons delete --name=name')

    mock_daemon_factory_load.assert_called_once_with('name',
                                                     logger=get_logger())

    daemon = mock_daemon_factory_load.return_value
    daemon.delete.assert_called_once_with()


def test_restart(mock_daemon_factory_new,
                 mock_daemon_factory_save,
                 mock_daemon_factory_load,
                 mock_daemon_factory_delete,
                 mock_daemon_factory_load_all,
                 mock_get_storage_dir):
    run_agent_command('cfy-agent daemons restart --name=name')

    mock_daemon_factory_load.assert_called_once_with('name',
                                                     logger=get_logger())

    daemon = mock_daemon_factory_load.return_value
    daemon.restart.assert_called_once_with()


def test_inspect(mock_daemon_factory_new,
                 mock_daemon_factory_save,
                 mock_daemon_factory_load,
                 mock_daemon_factory_delete,
                 mock_daemon_factory_load_all,
                 mock_daemon_api_internal_daemon_to_dict,
                 mock_get_storage_dir):

    mock_daemon_api_internal_daemon_to_dict.return_value = {}

    name = utils.internal.generate_agent_name()
    run_agent_command('cfy-agent daemons inspect --name={0}'.format(name))

    mock_daemon_factory_load.assert_called_once_with(name,
                                                     logger=get_logger())
    daemon = mock_daemon_factory_load.return_value

    mock_daemon_api_internal_daemon_to_dict.assert_called_once_with(daemon)


def test_status(mock_daemon_factory_new,
                mock_daemon_factory_save,
                mock_daemon_factory_load,
                mock_daemon_factory_delete,
                mock_daemon_factory_load_all,
                mock_get_storage_dir):
    name = utils.internal.generate_agent_name()
    run_agent_command('cfy-agent daemons status --name={0}'.format(name))
    daemon = mock_daemon_factory_load.return_value
    daemon.status.assert_called_once_with()


def test_required(mock_daemon_factory_new,
                  mock_daemon_factory_save,
                  mock_daemon_factory_load,
                  mock_daemon_factory_delete,
                  mock_daemon_factory_load_all,
                  mock_get_storage_dir):
    run_agent_command('cfy-agent daemons create --rest-host=manager '
                      '--broker-ip=manager '
                      '--process-management=init.d', raise_system_exit=True)


def test_inspect_non_existing_agent(mock_get_storage_dir):
    try:
        run_agent_command('cfy-agent daemons inspect --name=non-existing',
                          raise_system_exit=True)
    except SystemExit as e:
        assert e.code == 203


def test_list(mock_get_storage_dir):
    run_agent_command('cfy-agent daemons create '
                      '--process-management=init.d '
                      '--queue=queue --name=test-name --rest-host=127.0.0.1 '
                      '--broker-ip=127.0.0.1 --user=user ')
    run_agent_command('cfy-agent daemons create '
                      '--process-management=init.d '
                      '--queue=queue --name=test-name2 --rest-host=127.0.0.1 '
                      '--broker-ip=127.0.0.1 --user=user ')
    run_agent_command('cfy-agent daemons list')
