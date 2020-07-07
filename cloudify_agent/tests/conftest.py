import os

import pytest

from cloudify import mocks
from cloudify.state import current_ctx

from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.api.plugins import installer
from cloudify_agent.tests.agent_package_generator import AgentPackageGenerator
from cloudify_agent.tests import plugins
from cloudify_agent.tests.utils import (
    _AgentSSLCert,
    create_plugin_tar,
    create_plugin_wagon,
    FileServer,
    get_daemon_storage,
)


@pytest.fixture(scope='session', autouse=True)
def mock_ctx_with_tenant():
    original_ctx = current_ctx
    current_ctx.set(
        mocks.MockCloudifyContext(tenant={'name': 'default_tenant'}))
    yield current_ctx
    current_ctx.set(original_ctx)


@pytest.fixture(scope='function')
def agent_package():
    package = AgentPackageGenerator()
    yield package
    package.cleanup()


@pytest.fixture(scope='session')
def agent_ssl_cert(tmpdir_factory):
    yield _AgentSSLCert(tmpdir_factory.mktemp())


@pytest.fixture(scope='function')
def daemon_factory(tmp_path):
    yield DaemonFactory(storage=get_daemon_storage())


@pytest.fixture(scope='session')
def test_wagons(file_server):
    plugins_to_be_installed = [
        'mock-plugin',
        'mock-plugin-modified',
        'mock-plugin-with-requirements'
    ]
    wagons = {}
    for plugin_dir in plugins_to_be_installed:
        create_plugin_tar(
            plugin_dir_name=plugin_dir,
            target_directory=file_server.root_path)
        wagons[plugin_dir] = create_plugin_wagon(
            plugin_dir_name=plugin_dir,
            target_directory=file_server.root_path)
    yield wagons
    installer.uninstall_source(plugin=plugins.plugin_struct(''))
    installer.uninstall_source(plugin=plugins.plugin_struct(''),
                               deployment_id='deployment')
    installer.uninstall_wagon(plugins.PACKAGE_NAME, plugins.PACKAGE_VERSION)


@pytest.fixture(scope='session')
def file_server(tmp_path):
    server = FileServer(str(tmp_path), ssl=False)
    server.start()
    yield server
    server.stop()


def pytest_addoption(parser):
    """Tell the framework where to find the test file."""
    parser.addoption(
        '--run-ci-tests',
        action='store_true',
        default=False,
        help=(
            'Set this flag to run CI tests. '
            'These may contaminate the machine on which they run.'
        ),
    )


def pytest_collection_modifyitems(config, items):
    skip_ci = pytest.mark.skip(
        reason="CI tests may contaminate system. Set --run-ci-tests to run."
    )
    skip_os = pytest.mark.skip(
        reason='Not relevant OS to run the test.'
    )
    for item in items:
        if config.getoption('--run-ci-tests') and "only_ci" in item.keywords:
            item.add_marker(skip_ci)
        if "only_nt" in item.keywords and os.name != 'nt':
            item.add_marker(skip_os)
        if "only_posix" in item.keywords and os.name != 'posix':
            item.add_marker(skip_os)
