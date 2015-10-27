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

import tempfile

from mock import patch

from cloudify.workflows import local
from cloudify.utils import setup_logger

from cloudify_agent.tests import resources
from cloudify_agent.tests.utils import (
    FileServer,
    get_source_uri,
    get_requirements_uri)
from cloudify_agent.tests.api.pm import BaseDaemonLiveTestCase
from cloudify_agent.tests.api.pm import only_ci
from cloudify_agent.api import utils


##############################################################################
# these tests run a local workflow to install the agent on the local machine.
# it should support both windows and linux machines. and thus, testing the
# LocalWindowsAgentInstaller and LocalLinuxAgentInstaller.
# the remote use cases are tested as system tests because they require
# actually launching VM's from the test.
##############################################################################

class AgentInstallerLocalTest(BaseDaemonLiveTestCase):

    """
    these tests run local workflows in order to invoke the installer
    operations. the remote use case is tested as part of the system tests.
    """

    fs = None

    @classmethod
    def setUpClass(cls):
        cls.logger = setup_logger(cls.__name__)
        cls.resource_base = tempfile.mkdtemp(
            prefix='file-server-resource-base')
        cls.fs = FileServer(
            root_path=cls.resource_base)
        cls.fs.start()

        cls.source_url = get_source_uri()
        cls.requirements_file = get_requirements_uri()

    @classmethod
    def tearDownClass(cls):
        cls.fs.stop()

    @patch.dict('agent_packager.logger.LOGGER',
                disable_existing_loggers=False)
    @patch('cloudify.workflows.local._validate_node')
    @only_ci
    def test_local_agent_from_package(self, _):

        agent_name = utils.internal.generate_agent_name()
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
            'file_server_port': self.fs.port
        }

        env = local.init_env(name=self._testMethodName,
                             blueprint_path=blueprint_path,
                             inputs=inputs)

        env.execute('install', task_retries=0)
        self.assert_daemon_alive(name=agent_name)

        env.execute('uninstall', task_retries=1)
        self.wait_for_daemon_dead(name=agent_name)

    @only_ci
    @patch('cloudify.workflows.local._validate_node')
    @patch.dict('agent_packager.logger.LOGGER',
                disable_existing_loggers=False)
    def test_local_agent_from_source(self, _):

        agent_name = utils.internal.generate_agent_name()
        agent_queue = '{0}-queue'.format(agent_name)

        inputs = {
            'source_url': self.source_url,
            'requirements_file': self.requirements_file,
            'name': agent_name,
            'queue': agent_queue
        }

        blueprint_path = resources.get_resource(
            'blueprints/agent-from-source/local-agent-blueprint.yaml')
        self.logger.info('Initiating local env')
        env = local.init_env(name=self._testMethodName,
                             blueprint_path=blueprint_path,
                             inputs=inputs)

        env.execute('install', task_retries=0)
        self.assert_daemon_alive(name=agent_name)

        env.execute('uninstall', task_retries=1)
        self.wait_for_daemon_dead(name=agent_name)

    @only_ci
    @patch('cloudify.workflows.local._validate_node')
    @patch.dict('agent_packager.logger.LOGGER',
                disable_existing_loggers=False)
    def test_3_2_backwards(self, _):

        agent_name = utils.internal.generate_agent_name()
        agent_queue = '{0}-queue'.format(agent_name)

        inputs = {
            'source_url': self.source_url,
            'requirements_file': self.requirements_file,
            'name': agent_name,
            'queue': agent_queue
        }

        blueprint_path = resources.get_resource(
            'blueprints/3_2-agent-from-source/3_2-agent-from-source.yaml')
        self.logger.info('Initiating local env')
        env = local.init_env(name=self._testMethodName,
                             blueprint_path=blueprint_path,
                             inputs=inputs)

        env.execute('install', task_retries=0)
        self.assert_daemon_alive(name=agent_name)

        env.execute('uninstall', task_retries=1)
        self.wait_for_daemon_dead(name=agent_name)
