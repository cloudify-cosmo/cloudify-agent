import pytest

from cloudify_agent.tests.agent_package_generator import AgentPackageGenerator
from cloudify_agent.tests.utils import _AgentSSLCert, FileServer


@pytest.fixture(scope='function')
def agent_package():
    package = AgentPackageGenerator()
    yield package
    package.cleanup()


@pytest.fixture(scope='session')
def agent_ssl_cert(tmpdir_factory):
    yield _AgentSSLCert(tmpdir_factory.mktemp())


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
    if config.getoption('--run-ci-test'):
        return
    skip_ci = pytest.mark.skip(
        reason="CI tests may contaminate system. Set --run-ci-tests to run."
    )
    for item in items:
        if "only_ci" in item.keywords:
            item.add_marker(skip_ci)
