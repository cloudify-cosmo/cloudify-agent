import os

from mock import patch

from cloudify_agent.api.pm.detach import DetachedDaemon

from cloudify_agent.tests.api.pm import BaseDaemonProcessManagementTest
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.internal.get_storage_directory',
       get_storage_directory)
@pytest.mark.only_posix
class TestDetachedDaemon(BaseDaemonProcessManagementTest):

    @property
    def daemon_cls(self):
        return DetachedDaemon

    def test_configure(self):
        daemon = self.create_daemon()
        daemon.create()

        daemon.configure()
        assert os.path.exists(daemon.script_path)
        assert os.path.exists(daemon.config_path)

    def test_delete(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.stop()
        daemon.delete()
        assert not os.path.exists(daemon.script_path)
        assert not os.path.exists(daemon.config_path)
        assert not os.path.exists(daemon.pid_file)

    def test_cron_respawn(self):
        daemon = self.create_daemon(cron_respawn=True, cron_respawn_delay=1)
        daemon.create()
        daemon.configure()
        daemon.start()

        crontab = self.runner.run('crontab -l').std_out
        assert daemon.cron_respawn_path in crontab

        # lets kill the process
        self.runner.run("pkill -9 -f 'cloudify_agent.worker'")
        self.wait_for_daemon_dead(daemon.queue)

        # check it was respawned
        # mocking cron - respawn it using the cron respawn script
        self.runner.run(daemon.cron_respawn_path)
        self.wait_for_daemon_alive(daemon.queue)

        # this should also disable the crontab entry
        daemon.stop()
        self.wait_for_daemon_dead(daemon.queue)

        crontab = self.runner.run('crontab -l').std_out
        assert daemon.cron_respawn_path not in crontab
