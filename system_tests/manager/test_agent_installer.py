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

import os

from cloudify.utils import setup_logger

from system_tests import resources
from cosmo_tester.framework import testenv


class AgentInstallerTest(testenv.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.logger = setup_logger(
            'cloudify_agent.system_tests.manager.test_agent_installer')

    def test_3_2_agent(self):

        self.blueprint_yaml = resources.get_resource(
            '3-2-agent-blueprint/3-2-agent-mispelled-blprint.yaml')
        self.upload_deploy_and_execute_install(
            inputs={
                'image': self.env.ubuntu_image_id,
                'flavor': self.env.small_flavor_id
            }
        )
        self.execute_uninstall()

    def test_ssh_agent(self):

        self.blueprint_yaml = resources.get_resource(
            'ssh-agent-blueprint/ssh-agent-blueprint.yaml')
        self.upload_deploy_and_execute_install(
            inputs={
                'image': self.env.ubuntu_image_id,
                'flavor': self.env.small_flavor_id
            }
        )
        self.execute_uninstall()

    def test_userdata_agent(self):

        self.blueprint_yaml = resources.get_resource(
            'userdata-agent-blueprint/userdata-agent-blueprint.yaml')
        self.upload_deploy_and_execute_install(
            inputs={
                'image': self.env.ubuntu_image_id,
                'flavor': self.env.small_flavor_id,
                'branch': os.environ.get('BRANCH_NAME_CORE', 'master')
            }
        )
        self.execute_uninstall()

    def test_winrm_agent(self):

        self.blueprint_yaml = resources.get_resource(
            'winrm-agent-blueprint/winrm-agent-blueprint.yaml')
        self.upload_deploy_and_execute_install(
            inputs={
                'image': self.env.windows_image_id,
                'flavor': self.env.medium_flavor_id
            }
        )
        self.execute_uninstall()
