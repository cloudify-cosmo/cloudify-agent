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

import os
from mock import patch

from cloudify import constants

from cloudify_agent.installer.config import configuration
from cloudify_agent.tests.installer.config import mock_context
from cloudify_agent.tests.installer.config.test_configuration import \
    TestConfiguration


class TestSecuredConfiguration(TestConfiguration):

    def setUp(self):
        super(TestSecuredConfiguration, self).setUp()
        os.environ[constants.MANAGER_REST_PROTOCOL_KEY] = 'https'

    @patch('cloudify_agent.installer.config.configuration.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.attributes.ctx',
           mock_context())
    def test_prepare(self):

        cloudify_agent = {'local': True}
        configuration.prepare_connection(cloudify_agent)
        configuration.prepare_agent(cloudify_agent, None)

        expected = {
            'manager_ip': 'localhost',
            'manager_port': 8101,
            'manager_protocol': 'https',
        }
        self.assertDictContainsSubset(expected, cloudify_agent)
