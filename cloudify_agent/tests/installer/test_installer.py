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

from mock import Mock

from cloudify_agent.tests import BaseTest
import cloudify_agent.installer


class AgentInstallerTest(BaseTest):
    def test_broker_get_settings_from_manager_default(self):
        installer = cloudify_agent.installer.AgentInstaller(
            cloudify_agent={},
            logger=Mock(),
        )

        self.assertTrue(installer.broker_get_settings_from_manager)

    def test_broker_get_settings_from_manager_override_default(self):
        installer = cloudify_agent.installer.AgentInstaller(
            cloudify_agent={
                'broker_get_settings_from_manager': False,
            },
            logger=Mock(),
        )

        self.assertFalse(installer.broker_get_settings_from_manager)

    def test_broker_get_settings_from_manager_default_option(self):
        installer = cloudify_agent.installer.AgentInstaller(
            cloudify_agent={
                'process_management': {'name': 'fakemanagement'},
            },
            logger=Mock(),
        )

        options = installer._create_process_management_options()

        options = options.split(' ')

        self.assertIn(
            '--broker-get-settings-from-manager',
            options,
        )

    def test_broker_get_settings_from_manager_overridden_option(self):
        installer = cloudify_agent.installer.AgentInstaller(
            cloudify_agent={
                'broker_get_settings_from_manager': False,
                'process_management': {'name': 'fakemanagement'},
            },
            logger=Mock(),
        )

        options = installer._create_process_management_options()

        options = options.split(' ')

        self.assertNotIn(
            '--broker-get-settings-from-manager',
            options,
        )
