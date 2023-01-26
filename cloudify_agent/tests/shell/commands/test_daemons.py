from cloudify_agent.api import utils
from cloudify_agent.shell.main import get_logger
from cloudify_agent.tests.shell.commands import run_agent_command


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
