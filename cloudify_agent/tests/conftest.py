import pytest

from cloudify_agent.tests.agent_package_generator import AgentPackageGenerator
from cloudify_agent.tests.utils import _AgentSSLCert


@pytest.fixture(scope='function')
def agent_package():
    package = AgentPackageGenerator()
    yield package
    package.cleanup()


@pytest.fixture(scope='session')
def agent_ssl_cert(tmpdir_factory):
    yield _AgentSSLCert(tmpdir_factory.mktemp())
