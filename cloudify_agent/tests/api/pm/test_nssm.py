import os
import time

from mock import patch
import pytest

from cloudify.exceptions import CommandExecutionException

from cloudify_agent.api.pm.nssm import NonSuckingServiceManagerDaemon

from cloudify_agent.tests.api.pm import BaseDaemonProcessManagementTest
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.internal.get_storage_directory',
       get_storage_directory)
@pytest.mark.only_nt
class TestNonSuckingServiceManagerDaemon(BaseDaemonProcessManagementTest):

    @property
    def daemon_cls(self):
        return NonSuckingServiceManagerDaemon

    def test_configure(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        assert os.path.exists(daemon.config_path)

    def test_delete(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.stop()
        daemon.delete()
        assert not os.path.exists(daemon.config_path)
        pytest.raises(
            CommandExecutionException,
            self.runner.run,
            'sc getdisplayname {0}'.format(daemon.name))

    def test_status(self):
        daemon = self.create_daemon()
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
            self.fail('Daemon failed to start')
