import os
import socket

from mock import patch, MagicMock
import pytest

from cloudify import constants, mocks
from cloudify.state import current_ctx
from cloudify.tests.mocks.mock_rest_client import MockRestclient

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


@pytest.fixture(scope='function', autouse=True)
def base_test_management(agent_ssl_cert, tmp_path):
    # Mock the context for all tests
    original_ctx = current_ctx
    current_ctx.set(
        mocks.MockCloudifyContext(tenant={'name': 'default_tenant'}))

    # Make sure the right env vars are available for the agent
    agent_env_vars = {
        constants.MANAGER_FILE_SERVER_URL_KEY: 'localhost',
        constants.REST_HOST_KEY: 'localhost',
        constants.REST_PORT_KEY: '80',
        constants.BROKER_SSL_CERT_PATH: agent_ssl_cert.get_local_cert_path(),
        constants.LOCAL_REST_CERT_FILE_KEY: agent_ssl_cert.local_key_path(),
        constants.MANAGER_FILE_SERVER_ROOT_KEY: 'localhost/resources'
    }
    for key, value in agent_env_vars.items():
        os.environ[key] = value

    old_path = os.getcwd()
    os.chdir(str(tmp_path))

    yield current_ctx

    # Un-mock the context
    current_ctx.set(original_ctx)

    os.chdir(old_path)


@pytest.fixture(scope='function')
def agent_package():
    package = AgentPackageGenerator()
    yield package
    package.cleanup()


@pytest.fixture(scope='session')
def agent_ssl_cert(tmpdir_factory):
    yield _AgentSSLCert(str(tmpdir_factory.mktemp('agent_cert')))


@pytest.fixture(scope='function')
def daemon_factory(tmp_path):
    yield DaemonFactory(storage=get_daemon_storage(str(tmp_path)))


@pytest.fixture(scope='function')
def test_plugins(file_server):
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


@pytest.fixture(scope='function')
def file_server(tmp_path, agent_ssl_cert):
    base_path = os.path.join(str(tmp_path), 'fileserver')
    os.makedirs(base_path)
    server = FileServer(agent_ssl_cert, base_path, ssl=False)
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
    parser.addoption(
        '--run-rabbit-tests',
        action='store_true',
        default=False,
        help=(
            'Set this flag to run tests that require rabbit. '
            'You will need rabbit installed for these to work.'
        ),
    )


def pytest_collection_modifyitems(config, items):
    # It would be better to do this before collecting, but the hooks were
    # not co-operating.
    if config.getoption('--run-rabbit-tests'):
        try:
            socket.create_connection(('localhost', 5672), timeout=1)
        except (socket.error, socket.timeout) as err:
            raise RuntimeError(
                'Could not connect to rabbit on localhost:5672: '
                '{err}'.format(err=err)
            )

    skip_ci = pytest.mark.skip(
        reason="CI tests may contaminate system. Set --run-ci-tests to run."
    )
    skip_os = pytest.mark.skip(
        reason='Not relevant OS to run the test.'
    )
    skip_rabbit = pytest.mark.skip(
        reason='--run-rabbit-test not set. Install rabbit before using this.'
    )
    for item in items:
        if "only_rabbit" in item.keywords and not config.getoption(
                '--run-rabbit-tests'):
            item.add_marker(skip_rabbit)
        if "only_ci" in item.keywords and not config.getoption(
                '--run-ci-tests'):
            item.add_marker(skip_ci)
        if "only_nt" in item.keywords and os.name != 'nt':
            item.add_marker(skip_os)
        if "only_posix" in item.keywords and os.name != 'posix':
            item.add_marker(skip_os)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "only_ci: This test may contaminate the host system and should only "
        "be run on CI or a system you don't care about."
    )
    config.addinivalue_line(
        "markers",
        "only_rabbit: This test can only be run with a local rabbit server.",
    )
    config.addinivalue_line(
        "markers",
        "only_nt: This test can only be run on Windows systems.",
    )
    config.addinivalue_line(
        "markers",
        "only_posix: This test can only be run on Linux systems.",
    )


@pytest.fixture(scope='function')
def mock_delete_rmq_user():
    with patch(
        'cloudify_agent.installer.operations.delete_agent_rabbitmq_user'
    ) as deleter:
        yield deleter


@pytest.fixture(scope='function')
def mock_get_rest_client():
    with patch('cloudify.agent_utils.get_rest_client',
               return_value=MockRestclient()) as client:
        yield client


@pytest.fixture(scope='function')
def mock_is_agent_alive():
    with patch('cloudify_agent.api.utils.is_agent_alive',
               MagicMock(return_value=True)) as is_alive:
        yield is_alive


@pytest.fixture(scope='function')
def mock_send_amqp_task():
    with patch('cloudify_agent.operations._send_amqp_task') as sender:
        yield sender


@pytest.fixture(scope='function')
def mock_daemon_factory_new():
    with patch(
        'cloudify_agent.shell.commands.daemons.DaemonFactory.new'
    ) as df:
        yield df


@pytest.fixture(scope='function')
def mock_daemon_factory_save():
    with patch(
        'cloudify_agent.shell.commands.daemons.DaemonFactory.save'
    ) as df:
        yield df


@pytest.fixture(scope='function')
def mock_daemon_factory_load():
    with patch(
        'cloudify_agent.shell.commands.daemons.DaemonFactory.load'
    ) as df:
        yield df


@pytest.fixture(scope='function')
def mock_daemon_factory_delete():
    with patch(
        'cloudify_agent.shell.commands.daemons.DaemonFactory.delete'
    ) as df:
        yield df


@pytest.fixture(scope='function')
def mock_daemon_factory_load_all():
    with patch(
        'cloudify_agent.shell.commands.daemons.DaemonFactory.load_all'
    ) as df:
        yield df


@pytest.fixture(scope='function')
def mock_daemon_api_internal_daemon_to_dict():
    with patch(
        'cloudify_agent.shell.commands.daemons.api_utils'
        '.internal.daemon_to_dict'
    ) as idtd:
        yield idtd


@pytest.fixture(scope='function')
def mock_get_storage_dir(get_storage_directory):
    with patch('cloudify_agent.api.utils.internal.get_storage_directory',
               return_value=get_storage_directory) as get_storage:
        yield get_storage


@pytest.fixture(scope='function')
def get_storage_directory(tmp_path):
    yield os.path.join(str(tmp_path), 'cfy-agent-tests-daemons')
