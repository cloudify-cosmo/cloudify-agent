#########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

import shutil
import tempfile
import uuid

from mock import patch
from testtools import TestCase

from cloudify.workflows import local
from cloudify.utils import setup_logger
from cloudify.tests.mocks.mock_rest_client import MockRestclient

from cloudify_agent.api import utils
from cloudify_agent.tests import resources, agent_ssl_cert
from cloudify_agent.tests.utils import (
    FileServer,
    get_source_uri,
    get_requirements_uri)
from cloudify_agent.tests.api.pm import (
    only_ci,
    only_os,
    BaseDaemonLiveTestCase
)
from cloudify_agent.tests.installer.config import get_tenant_mock
from cloudify_rest_client.manager import ManagerItem

##############################################################################
# these tests run a local workflow to install the agent on the local machine.
# it should support both windows and linux machines. and thus, testing the
# LocalWindowsAgentInstaller and LocalLinuxAgentInstaller.
# the remote use cases are tested as system tests because they require
# actually launching VM's from the test.
##############################################################################


class TestAgentInstallerLocal(BaseDaemonLiveTestCase, TestCase):
    """
    these tests run local workflows in order to invoke the installer
    operations. the remote use case is tested as part of the system tests.
    """

    @classmethod
    def setUpClass(cls):
        cls.logger = setup_logger(cls.__name__)
        cls.source_url = get_source_uri()
        cls.requirements_file = get_requirements_uri()

    def setUp(self):
        super(TestAgentInstallerLocal, self).setUp()

        self.resource_base = tempfile.mkdtemp(
            prefix='file-server-resource-base')
        self.fs = FileServer(root_path=self.resource_base, ssl=False)
        self.fs.start()

        self.addCleanup(self.fs.stop)
        self.addCleanup(shutil.rmtree, self.resource_base)

    @only_os('posix')
    @only_ci
    def test_local_agent_from_package_posix(self):
        # Check that agent still works with a filepath longer than 128 bytes
        # (paths longer than 128 bytes break shebangs on linux.)
        agent_name = 'agent-' + ''.join(uuid.uuid4().hex for _ in range(4))
        self._test_local_agent_from_package(agent_name)

    @only_os('nt')
    @only_ci
    def test_local_agent_from_package_nt(self):
        agent_name = utils.internal.generate_agent_name()
        self._test_local_agent_from_package(agent_name)

    @patch('cloudify.workflows.local._validate_node')
    @patch('cloudify_agent.installer.operations.delete_agent_rabbitmq_user')
    @patch('cloudify.agent_utils.get_rest_client',
           return_value=MockRestclient())
    @get_tenant_mock()
    @patch('cloudify.utils.get_manager_name', return_value='cloudify')
    def _test_local_agent_from_package(self, agent_name, *_):

        agent_queue = '{0}-queue'.format(agent_name)

        blueprint_path = resources.get_resource(
            'blueprints/agent-from-package/local-agent-blueprint.yaml')
        self.logger.info('Initiating local env')

        inputs = {
            'resource_base': self.resource_base,
            'source_url': self.source_url,
            'requirements_file': self.requirements_file,
            'name': agent_name,
            'queue': agent_queue,
            'file_server_port': self.fs.port,
            'ssl_cert_path': self._rest_cert_path
        }
        managers = [
            ManagerItem({
                'networks': {'default': '127.0.0.1'},
                'ca_cert_content': agent_ssl_cert.DUMMY_CERT,
                'hostname': 'cloudify'
            })
        ]

        with patch('cloudify.endpoint.LocalEndpoint.get_managers',
                   return_value=managers):
            env = local.init_env(name=self._testMethodName,
                                 blueprint_path=blueprint_path,
                                 inputs=inputs)

            env.execute('install', task_retries=0)
        agent_dict = self.get_agent_dict(env)
        agent_ssl_cert.verify_remote_cert(agent_dict['agent_dir'])

        env.execute('uninstall', task_retries=1)
        self.wait_for_daemon_dead(agent_queue)
