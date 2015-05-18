#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
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

import os
import tempfile

from mock import patch

from cloudify.workflows import local
from cloudify.utils import setup_logger
from cloudify import constants

import cloudify_agent
from cloudify_agent.api import utils

from cloudify_agent.tests import resources
from cloudify_agent.tests import utils as test_utils
from cloudify_agent.tests.api.pm import BaseDaemonLiveTestCase
from cloudify_agent.tests.utils import env as cenv
from cloudify_agent.tests.api.pm import only_ci
from cloudify_agent.tests.api.pm import only_os


##############################################################################
# these tests run a local workflow to install the agent on the local machine.
# it should support both windows and linux machines. and thus, testing the
# LocalWindowsAgentInstaller and LocalLinuxAgentInstaller.
# the remote use cases are tested as system tests because they require
# actually launching VM's from the test.
##############################################################################

class AgentInstallerLocalTest(BaseDaemonLiveTestCase):

    fs = None

    @classmethod
    def setUpClass(cls):
        cls.logger = setup_logger('test_tasks')
        cls.resource_base = tempfile.mkdtemp(
            prefix='file-server-resource-base')
        cls.fs = test_utils.FileServer(
            root_path=cls.resource_base)
        cls.fs.start()
        project_dir = os.path.dirname(
            os.path.dirname(cloudify_agent.__file__))

        cls.source_url = project_dir
        cls.requirements_file = os.path.join(
            project_dir, 'dev-requirements.txt')

    @classmethod
    def tearDownClass(cls):
        cls.fs.stop()

    @patch('cloudify.workflows.local._validate_node')
    @only_ci
    @only_os('posix')
    def test_local_agent_from_package(self, _):

        agent_name = utils.generate_agent_name()

        blueprint_path = resources.get_resource(
            'blueprints/agent-from-package/local-agent-blueprint.yaml')
        self.logger.info('Initiating local env')

        inputs = {
            'resource_base': self.resource_base,
            'source_url': self.source_url,
            'requirements_file': self.requirements_file,
            'name': agent_name
        }

        env = local.init_env(name=self._testMethodName,
                             blueprint_path=blueprint_path,
                             inputs=inputs)

        env.execute('install', task_retries=0)
        self.assert_daemon_alive(name=agent_name)

        # this needs to be executed with the AGENT_NAME_KEY environment
        # variable to correctly simulate the execution of the 'stop' method
        # as if it was inside the agent process itself
        with cenv(constants.AGENT_NAME_KEY, agent_name):
            env.execute('uninstall', task_retries=12)
            self.wait_for_daemon_dead(name=agent_name)

    @only_ci
    @patch('cloudify.workflows.local._validate_node')
    def test_local_agent_from_source(self, _):

        agent_name = utils.generate_agent_name()

        inputs = {
            'source_url': self.source_url,
            'requirements_file': self.requirements_file,
            'name': agent_name
        }

        blueprint_path = resources.get_resource(
            'blueprints/agent-from-source/local-agent-blueprint.yaml')
        self.logger.info('Initiating local env')
        env = local.init_env(name=self._testMethodName,
                             blueprint_path=blueprint_path,
                             inputs=inputs)

        env.execute('install', task_retries=0)
        self.assert_daemon_alive(name=agent_name)

        # this needs to be executed with the AGENT_NAME_KEY environment
        # variable to correctly simulate the execution of the 'stop' method
        # as if it was inside the agent process itself
        with cenv(constants.AGENT_NAME_KEY, agent_name):
            env.execute('uninstall', task_retries=12)
            self.wait_for_daemon_dead(name=agent_name)
