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
from cloudify import ctx
from cloudify import mocks

from cloudify.exceptions import NonRecoverableError

from cloudify.state import current_ctx

from cloudify_agent import operations
from cloudify_agent.installer.config import configuration

from cloudify_agent.tests import utils
from cloudify_agent.tests import BaseTest

from cloudify_agent.tests.installer.config import mock_context


class TestOperations(BaseTest):

    """
    Note that this test case only tests the utility methods inside
    this module. the operation themselves are tested as part of a system test.
    unfortunately the operations cannot currently be unittested because
    they use the ctx object and they cannot be exeucted as local workflows.
    """

    def test_get_url_and_args_http_no_args(self):
        plugin = {'source': 'http://google.com'}
        url = operations.get_plugin_source(plugin)
        args = operations.get_plugin_args(plugin)
        self.assertEqual(url, 'http://google.com')
        self.assertEqual(args, '')

    def test_get_url_https(self):
        plugin = {
            'source': 'https://google.com',
            'install_arguments': '--pre'
        }
        url = operations.get_plugin_source(plugin)
        args = operations.get_plugin_args(plugin)

        self.assertEqual(url, 'https://google.com')
        self.assertEqual(args, '--pre')

    def test_get_url_faulty_schema(self):
        self.assertRaises(NonRecoverableError,
                          operations.get_plugin_source,
                          {'source': 'bla://google.com'})

    def test_get_plugin_source_from_blueprints_dir(self):
        plugin = {
            'source': 'plugin-dir-name'
        }
        with utils.env(constants.MANAGER_FILE_SERVER_BLUEPRINTS_ROOT_URL_KEY,
                       'localhost'):
            source = operations.get_plugin_source(
                plugin,
                blueprint_id='blueprint_id')
        self.assertEqual(
            'localhost/blueprint_id/plugins/plugin-dir-name.zip',
            source)


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
            'ip': '10.0.4.47',
            'manager_ip': '10.0.4.46',
            'distro': 'ubuntu',
            'distro_codename': 'trusty',
            'basedir': '/home/vagrant',
            'user': 'vagrant',
            'key': '~/.ssh/id_rsa',
            'windows': False,
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
            properties={'cloudify_agent': {}})
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
        equal_keys = ['ip', 'distro', 'distro_codename', 'basedir', 'user']
        for k in equal_keys:
            self.assertEqual(old_agent[k], new_agent[k])
        nonequal_keys = ['package_url', 'agent_dir', 'workdir',
                         'envdir', 'name', 'manager_ip']
        for k in nonequal_keys:
            self.assertNotEqual(old_agent[k], new_agent[k])

    @patch('cloudify_agent.operations.celery.Celery', MagicMock())
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
        finally:
            current_ctx.set(old_context)
