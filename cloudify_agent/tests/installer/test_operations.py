import logging

from mock import patch
import pytest

from cloudify.workflows import local
from cloudify.utils import setup_logger
from cloudify.tests.mocks.mock_rest_client import MockRestclient

from cloudify_agent.api import utils
from cloudify_agent.tests import resources
from cloudify_agent.tests.utils import (
    get_source_uri,
    get_requirements_uri)
from cloudify_agent.tests import get_agent_dict
from cloudify_agent.tests.daemon import wait_for_daemon_dead
from cloudify_agent.tests.installer.config import get_tenant_mock
from cloudify_rest_client.manager import ManagerItem


logger = setup_logger(
    'cloudify-agent.tests.installer.test_operations',
    logger_level=logging.DEBUG)


##############################################################################
# these tests run a local workflow to install the agent on the local machine.
# it should support both windows and linux machines. and thus, testing the
# LocalWindowsAgentInstaller and LocalLinuxAgentInstaller.
# the remote use cases are tested as system tests because they require
# actually launching VMs from the test.
##############################################################################

@pytest.mark.only_posix
@pytest.mark.only_ci
def test_local_agent_from_package_posix(file_server, tmp_path,
                                        agent_ssl_cert, request):
    # Check that agent still works with a filepath longer than 128 bytes
    # (paths longer than 128 bytes break shebangs on linux.)
    agent_name = 'agent-{0}'.format(''.join('a' for _ in range(128)))
    _test_local_agent_from_package(agent_name, file_server, agent_ssl_cert,
                                   request)


@pytest.mark.only_nt
@pytest.mark.only_ci
def test_local_agent_from_package_nt(file_server, tmp_path, agent_ssl_cert,
                                     request):
    agent_name = utils.internal.generate_agent_name()
    _test_local_agent_from_package(agent_name, file_server, agent_ssl_cert,
                                   request)


@patch('cloudify.workflows.local._validate_node')
@patch('cloudify_agent.installer.operations.delete_agent_rabbitmq_user')
@patch('cloudify.agent_utils.get_rest_client',
       return_value=MockRestclient())
@get_tenant_mock()
@patch('cloudify.utils.get_manager_name', return_value='cloudify')
def _test_local_agent_from_package(agent_name, fs, ssl_cert, request, *_):

    agent_queue = '{0}-queue'.format(agent_name)

    blueprint_path = resources.get_resource(
        'blueprints/agent-from-package/local-agent-blueprint.yaml')
    logger.info('Initiating local env')

    inputs = {
        'resource_base': fs.root_path,
        'source_url': get_source_uri(),
        'requirements_file': get_requirements_uri(),
        'name': agent_name,
        'queue': agent_queue,
        'file_server_port': fs.port,
        'ssl_cert_path': ssl_cert.local_cert_path()
    }
    managers = [
        ManagerItem({
            'networks': {'default': '127.0.0.1'},
            'ca_cert_content': ssl_cert.DUMMY_CERT,
            'hostname': 'cloudify'
        })
    ]

    with patch('cloudify.endpoint.LocalEndpoint.get_managers',
               return_value=managers):
        env = local.init_env(name=request.node.name,
                             blueprint_path=blueprint_path,
                             inputs=inputs)

        env.execute('install', task_retries=0)
    agent_dict = get_agent_dict(env)
    ssl_cert.verify_remote_cert(agent_dict['agent_dir'])

    env.execute('uninstall', task_retries=1)
    wait_for_daemon_dead(agent_queue)
