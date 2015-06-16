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

from cloudify_agent.installer.runners import winrm_runner

from cloudify_agent.tests import BaseTest

##############################################################################
# note that this file only tests validation and defaults of the fabric runner.
# it does not test the actual functionality because that requires starting
# a vm. functional tests are executed as local workflow tests in the system
# tests framework
##############################################################################


class TestValidations(BaseTest):

    def test_validate_host(self):

        # Missing host
        session_config = {
            'user': 'test_user',
            'password': 'test_password'
        }

        try:
            winrm_runner.validate(session_config)
            self.fail('Expected ValueError for missing host')
        except ValueError as e:
            self.assertIn('Invalid host', e.message)

    def test_validate_user(self):

        # Missing user
        session_config = {
            'host': 'test_host',
            'password': 'test_password'
        }

        try:
            winrm_runner.validate(session_config)
            self.fail('Expected ValueError for missing user')
        except ValueError as e:
            self.assertIn('Invalid user', e.message)

    def test_validate_password(self):

        # Missing password
        session_config = {
            'host': 'test_host',
            'user': 'test_user'
        }

        try:
            winrm_runner.validate(session_config)
            self.fail('Expected ValueError for missing password')
        except ValueError as e:
            self.assertIn('Invalid password', e.message)


class TestDefaults(BaseTest):

    def test_defaults(self):

        runner = winrm_runner.WinRMRunner(
            validate_connection=False,
            host='test_host',
            user='test_user',
            password='test_password')

        self.assertEquals(
            runner.session_config['protocol'],
            winrm_runner.DEFAULT_WINRM_PROTOCOL)
        self.assertEquals(
            runner.session_config['uri'],
            winrm_runner.DEFAULT_WINRM_URI)
        self.assertEquals(
            runner.session_config['port'],
            winrm_runner.DEFAULT_WINRM_PORT)
