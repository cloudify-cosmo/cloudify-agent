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

from cloudify_agent.installer import exceptions
from cloudify_agent.installer.runners.fabric_runner import FabricRunner

from cloudify_agent.tests import BaseTest

##############################################################################
# note that this file only tests validation and defaults of the fabric runner.
# it does not test the actual functionality because that requires starting
# a vm. functional tests are executed as local workflow tests in the system
# tests framework
##############################################################################


class TestDefaults(BaseTest):

    def test_default_port(self):
        runner = FabricRunner(
            validate_connection=False,
            user='user',
            host='host',
            password='password')
        self.assertTrue(runner.port, 22)


class TestValidations(BaseTest):

    def test_no_host(self):
        self.assertRaisesRegexp(
            exceptions.AgentInstallerConfigurationError,
            'Missing host',
            FabricRunner,
            validate_connection=False,
            user='user',
            password='password')

    def test_no_user(self):
        self.assertRaisesRegexp(
            exceptions.AgentInstallerConfigurationError,
            'Missing user',
            FabricRunner,
            validate_connection=False,
            host='host',
            password='password')

    def test_key_and_password(self):
        self.assertRaisesRegexp(
            exceptions.AgentInstallerConfigurationError,
            'Cannot specify both key and password',
            FabricRunner,
            validate_connection=False,
            host='host',
            user='user',
            password='password',
            key='key')

    def test_no_key_no_password(self):
        self.assertRaisesRegexp(
            exceptions.AgentInstallerConfigurationError,
            'Must specify either key or password',
            FabricRunner,
            validate_connection=False,
            host='host',
            user='password')
