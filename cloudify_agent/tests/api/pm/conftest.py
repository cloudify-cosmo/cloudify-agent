import os

import pytest

from cloudify.utils import setup_logger

from cloudify_agent.api import utils
from cloudify_agent.api.plugins import installer
from cloudify_agent.tests.api.pm import DEPLOYMENT_ID
from cloudify_agent.tests.api.pm.daemons import (
    TestDetachedDaemon,
    TestInitdDaemon,
    TestNSSMDaemon,
)

logger = setup_logger('cloudify_agent.tests.api.pm')


@pytest.fixture(scope='function', autouse=True)
def always_mock_storage_dir(mock_get_storage_dir):
    yield


@pytest.fixture(scope='function')
def detach_daemon(tmp_path, agent_ssl_cert):
    daemon = TestDetachedDaemon(tmp_path, logger, agent_ssl_cert)

    yield daemon

    daemon.runner.run("pkill -9 -f 'cloudify_agent.worker'",
                      exit_on_failure=False)
    installer.uninstall_source(plugin=daemon.plugin_struct())
    installer.uninstall_source(plugin=daemon.plugin_struct(),
                               deployment_id=DEPLOYMENT_ID)
    for _daemon in daemon.daemons:
        daemon.factory.delete(_daemon.name)


@pytest.fixture(scope='function')
def initd_daemon(tmp_path, agent_ssl_cert):
    daemon = TestInitdDaemon(tmp_path, logger, agent_ssl_cert)

    yield daemon

    daemon.runner.run("pkill -9 -f 'cloudify_agent.worker'",
                      exit_on_failure=False)
    installer.uninstall_source(plugin=daemon.plugin_struct())
    installer.uninstall_source(plugin=daemon.plugin_struct(),
                               deployment_id=DEPLOYMENT_ID)
    for _daemon in daemon.daemons:
        daemon.factory.delete(_daemon.name)


@pytest.fixture(scope='function')
def nssm_daemon(tmp_path, agent_ssl_cert):
    daemon = TestNSSMDaemon(tmp_path, logger, agent_ssl_cert)

    yield daemon

    nssm_path = utils.get_absolute_resource_path(
        os.path.join('pm', 'nssm', 'nssm.exe'))
    for _daemon in daemon.daemons:
        daemon.runner.run('sc stop {0}'.format(_daemon.name),
                          exit_on_failure=False)
        daemon.runner.run('{0} remove {1} confirm'.format(nssm_path,
                                                          _daemon.name),
                          exit_on_failure=False)
    installer.uninstall_source(plugin=daemon.plugin_struct())
    installer.uninstall_source(plugin=daemon.plugin_struct(),
                               deployment_id=DEPLOYMENT_ID)
    for _daemon in daemon.daemons:
        daemon.factory.delete(_daemon.name)
