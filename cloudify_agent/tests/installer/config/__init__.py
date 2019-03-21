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

from mock import MagicMock

from cloudify.context import BootstrapContext
from cloudify.mocks import MockCloudifyContext


def mock_get_brokers(*args, **kwargs):
    return [
        {
            'host': '127.0.0.1',
            'ca_cert_content': '',
        },
    ]


def mock_context(agent_properties=None,
                 agent_runtime_properties=None,
                 agent_context=None):

    agent_context = agent_context or {}
    agent_properties = agent_properties or {}
    agent_runtime_properties = agent_runtime_properties or {}

    context = MockCloudifyContext(
        node_id='test_node',
        node_name='test_node',
        blueprint_id='test_blueprint',
        deployment_id='test_deployment',
        execution_id='test_execution',
        rest_token='test_token',
        properties={'cloudify_agent': agent_properties},
        runtime_properties={'cloudify_agent': agent_runtime_properties},
        bootstrap_context=BootstrapContext(
            bootstrap_context={'cloudify_agent': agent_context})
    )
    context.installer = MagicMock()
    context.get_brokers = mock_get_brokers
    context._get_current_object = lambda: context
    return context
