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
