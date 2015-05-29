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

import unittest2 as unittest
from mock import patch

from cloudify_agent.installer.config import decorators

from cloudify_agent.tests.installer.config import mock_context


class TestConfigDecorators(unittest.TestCase):

    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.decorators.AGENT_ATTRIBUTES',
           {'attr': {}})
    def test_in_invocation_before(self):

        @decorators.attribute('attr')
        def attr(_):
            pass

        cloudify_agent = {'attr': 'value'}
        attr(cloudify_agent)

        self.assertEqual(cloudify_agent['attr'], 'value')

    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.decorators.AGENT_ATTRIBUTES',
           {'attr': {}})
    def test_in_invocation_after(self):

        @decorators.attribute('attr')
        def attr(_):
            return 'value'

        cloudify_agent = {}
        attr(cloudify_agent)

        self.assertEqual(cloudify_agent['attr'], 'value')

    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context(
               agent_runtime_properties={'attr': 'value'}))
    @patch('cloudify_agent.installer.config.decorators.AGENT_ATTRIBUTES',
           {'attr': {}})
    def test_in_runtime_properties(self):

        @decorators.attribute('attr')
        def attr(_):
            pass

        cloudify_agent = {}
        attr(cloudify_agent)

        self.assertEqual(cloudify_agent['attr'], 'value')

    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context(
               agent_properties={'attr': 'value'}))
    @patch('cloudify_agent.installer.config.decorators.AGENT_ATTRIBUTES',
           {'attr': {}})
    def test_in_properties(self):

        @decorators.attribute('attr')
        def attr(_):
            pass

        cloudify_agent = {}
        attr(cloudify_agent)

        self.assertEqual(cloudify_agent['attr'], 'value')

    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context(agent_context={'user': 'value'}))
    def test_in_agent_context(self):

        @decorators.attribute('user')
        def attr(_):
            pass

        cloudify_agent = {}
        attr(cloudify_agent)

        self.assertEqual(cloudify_agent['user'], 'value')

    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context(agent_properties={'attr': 'value'}))
    @patch('cloudify_agent.installer.config.decorators.AGENT_ATTRIBUTES',
           {'attr': {}})
    def test_invocation_overrides_properties(self):

        @decorators.attribute('attr')
        def attr(_):
            pass

        cloudify_agent = {'attr': 'value-overridden'}
        attr(cloudify_agent)

        self.assertEqual(cloudify_agent['attr'], 'value-overridden')

    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context(agent_context={'attr': 'value'}))
    @patch('cloudify_agent.installer.config.decorators.AGENT_ATTRIBUTES',
           {'attr': {}})
    def test_invocation_overrides_context(self):

        @decorators.attribute('attr')
        def attr(_):
            pass

        cloudify_agent = {'attr': 'value-overridden'}
        attr(cloudify_agent)

        self.assertEqual(cloudify_agent['attr'], 'value-overridden')

    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context(agent_properties={'attr': 'value-overridden'},
                        agent_context={'attr': 'value'}))
    @patch('cloudify_agent.installer.config.decorators.AGENT_ATTRIBUTES',
           {'attr': {}})
    def test_properties_override_context(self):

        @decorators.attribute('attr')
        def attr(_):
            pass

        cloudify_agent = {}
        attr(cloudify_agent)

        self.assertEqual(cloudify_agent['attr'], 'value-overridden')

    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context(
               agent_properties={
                   'attr1': 'value1',
                   'attr2': 'value2'
               },
               agent_runtime_properties={
                   'attr1': 'value1-override'
               }))
    @patch('cloudify_agent.installer.config.decorators.AGENT_ATTRIBUTES',
           {'attr1': {'group': 'g'}, 'attr2': {'group': 'g'}})
    def test_group(self):

        @decorators.group('g')
        def g(_):
            pass

        cloudify_agent = {}
        g(cloudify_agent)

        self.assertEqual(cloudify_agent['attr1'], 'value1-override')
        self.assertEqual(cloudify_agent['attr2'], 'value2')

    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context(agent_properties={
               'attr1': 'value1', 'attr2': 'value2'}))
    @patch('cloudify_agent.installer.config.decorators.AGENT_ATTRIBUTES',
           {'attr1': {'group': 'g'}, 'attr2': {'group': 'g'}})
    def test_apply_group_function(self):

        @decorators.group('g')
        def g(_):
            _['attr3'] = 'value3'

        cloudify_agent = {}
        g(cloudify_agent)

        self.assertEqual(cloudify_agent['attr1'], 'value1')
        self.assertEqual(cloudify_agent['attr2'], 'value2')
        self.assertEqual(cloudify_agent['attr3'], 'value3')
