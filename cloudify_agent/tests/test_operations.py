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

from mock import patch, MagicMock

from cloudify import constants
from cloudify import context
from cloudify import ctx
from cloudify import mocks

from cloudify.state import current_ctx

from cloudify_agent import operations
from cloudify_agent.installer.config import configuration

from cloudify_agent.tests import BaseTest
from cloudify_agent.tests.installer.config import mock_context


celery_mock = MagicMock()


class TestCreateAgentAmqp(BaseTest):

    @patch('cloudify_agent.installer.config.configuration.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.attributes.ctx',
           mock_context())
    def _create_agent(self):
        old_agent = {
            'local': False,
            'remote_execution': False,
            'ip': '10.0.4.47',
            'manager_ip': '10.0.4.46',
            'distro': 'ubuntu',
            'distro_codename': 'trusty',
            'basedir': '/home/vagrant',
            'user': 'vagrant',
            'key': '~/.ssh/id_rsa',
            'windows': False,
            'broker_pass': 'test_pass',
            'package_url': 'http://10.0.4.46:53229/packages/agents/'
                           'ubuntu-trusty-agent.tar.gz',
        }
        configuration.prepare_connection(old_agent)
        configuration.prepare_agent(old_agent, None)
        return old_agent

    def _create_node_instance_context(self):
        properties = {}
        properties['cloudify_agent'] = self._create_agent()
        mock = mocks.MockCloudifyContext(
            node_id='host_af231',
            runtime_properties=properties,
            node_name='host',
            properties={'cloudify_agent': {}},
            bootstrap_context=context.BootstrapContext({
                'cloudify_agent': {
                    'broker_user': 'test_user'}}))
        return mock

    def _patch_manager_env(self):
        new_env = {
            constants.MANAGER_IP_KEY: '10.0.4.48',
            constants.MANAGER_FILE_SERVER_URL_KEY: 'http://10.0.4.48:53229'
        }
        return patch.dict(os.environ, new_env)

    @patch('cloudify_agent.installer.config.configuration.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.attributes.ctx',
           mock_context())
    def test_create_agent_dict(self):
        old_agent = self._create_agent()
        with self._patch_manager_env():
            new_agent = operations.create_new_agent_dict(old_agent)
            third_agent = operations.create_new_agent_dict(new_agent)
        equal_keys = ['ip', 'basedir', 'user']
        for k in equal_keys:
            self.assertEqual(old_agent[k], new_agent[k])
            self.assertEqual(old_agent[k], third_agent[k])
        nonequal_keys = ['agent_dir', 'workdir',
                         'envdir', 'name', 'manager_ip']
        for k in nonequal_keys:
            self.assertNotEqual(old_agent[k], new_agent[k])
            self.assertNotEqual(old_agent[k], third_agent[k])
        old_name = old_agent['name']
        new_name = new_agent['name']
        third_name = third_agent['name']
        self.assertIn(old_name, new_name)
        self.assertIn(old_name, third_name)
        self.assertLessEqual(len(third_name), len(new_name))
        new_agent['name'] = '{0}{1}'.format(new_agent['name'], 'not-uuid')
        with self._patch_manager_env():
            agent = operations.create_new_agent_dict(new_agent)
            self.assertIn(new_agent['name'], agent['name'])

    @patch('cloudify_agent.operations.celery.Celery', celery_mock)
    @patch('cloudify_agent.operations.app', MagicMock())
    def test_create_agent_from_old_agent(self):
        context = self._create_node_instance_context()
        old_context = ctx
        current_ctx.set(context)
        try:
            old_name = ctx.instance.runtime_properties[
                'cloudify_agent']['name']
            old_agent_dir = ctx.instance.runtime_properties[
                'cloudify_agent']['agent_dir']
            old_queue = ctx.instance.runtime_properties[
                'cloudify_agent']['queue']

            with self._patch_manager_env():
                operations.create_agent_from_old_agent()
            new_name = ctx.instance.runtime_properties[
                'cloudify_agent']['name']
            new_agent_dir = ctx.instance.runtime_properties[
                'cloudify_agent']['agent_dir']
            new_queue = ctx.instance.runtime_properties[
                'cloudify_agent']['queue']
            self.assertNotEquals(old_name, new_name)
            self.assertNotEquals(old_agent_dir, new_agent_dir)
            self.assertNotEquals(old_queue, new_queue)
            broker_url = 'amqp://test_user:test_pass@10.0.4.46:5672//'
            celery_mock.assert_called_with(broker=broker_url,
                                           backend=broker_url)
        finally:
            current_ctx.set(old_context)
