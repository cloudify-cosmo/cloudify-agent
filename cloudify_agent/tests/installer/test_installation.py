########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

from mock import patch
from testtools import TestCase

from cloudify_agent.tests.resources import get_resource

from cloudify.workflows import local

from cloudify_agent.installer import AgentInstaller


class InstallAgentTest(TestCase):
    """
    These tests validate that when using older blueprints (3.2), the new
    cloudify_agent operations are invoked
    """
    # Patch _validate_node, to allow installing agent in local mode
    @patch('cloudify.workflows.local._validate_node')
    @patch('cloudify_agent.installer.operations.start')
    @patch('cloudify_agent.installer.operations.configure')
    @patch('cloudify_agent.installer.operations.create')
    def _test_install_agent(self,
                            blueprint,
                            create_mock,
                            config_mock,
                            start_mock, *_):
        blueprint_path = get_resource(
            'blueprints/install-agent/{0}'.format(blueprint)
        )
        env = local.init_env(blueprint_path)
        env.execute('install')

        create_mock.assert_has_any_calls()
        config_mock.assert_has_any_calls()
        start_mock.assert_has_any_calls()

    def test_install_agent(self):
        self._test_install_agent('test-install-agent-blueprint.yaml')

    def test_install_agent_windows(self):
        self._test_install_agent('test-install-agent-blueprint-windows.yaml')

    def test_install_agent_3_2(self):
        self._test_install_agent('test-install-agent-blueprint-3-2.yaml')

    def test_install_agent_windows_3_2(self):
        self._test_install_agent(
            'test-install-agent-blueprint-windows-3-2.yaml')

    def test_create_process_management_options(self):
        def _test_param(value, expected=None):
            installer = AgentInstaller({
                'process_management': {
                    'name': 'nssm',
                    'param': value,
                }
            })
            result = installer._create_process_management_options()
            self.assertEquals(result, "--param={0}".format(expected or value))

        _test_param('value1')
        _test_param('value2with$sign', "'value2with$sign'")
