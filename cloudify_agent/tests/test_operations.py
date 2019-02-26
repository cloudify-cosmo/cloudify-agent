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
import platform
import shutil
import unittest
from contextlib import contextmanager

from mock import patch, MagicMock

from cloudify import constants
from cloudify import context
from cloudify import ctx
from cloudify import mocks

from cloudify.state import current_ctx
from cloudify.workflows import local
from cloudify.amqp_client import get_client
from cloudify.tests.mocks.mock_rest_client import MockRestclient

from cloudify_agent import operations
from cloudify_agent.api import utils
from cloudify_agent.installer.config.agent_config import CloudifyAgentConfig

from cloudify_agent.tests import agent_ssl_cert
from cloudify_agent.tests import BaseTest, resources, agent_package
from cloudify_agent.tests.installer.config import mock_context
from cloudify_agent.tests.utils import FileServer

from cloudify_agent.tests.api.pm import BaseDaemonLiveTestCase
from cloudify_agent.tests.api.pm import only_ci


class TestInstallNewAgent(BaseDaemonLiveTestCase, unittest.TestCase):
    def setUp(self):
        super(TestInstallNewAgent, self).setUp()

    @contextmanager
    def _manager_env(self):
        port = 8756
        fs = FileServer(root_path=self.temp_folder, port=port)
        fs.start()
        if os.name == 'nt':
            package_name = 'cloudify-windows-agent.exe'
        else:
            dist = platform.dist()
            package_name = '{0}-{1}-agent.tar.gz'.format(dist[0].lower(),
                                                         dist[2].lower())
        resources_dir = os.path.join(self.temp_folder, 'resources')
        agent_dir = os.path.join(resources_dir, 'packages', 'agents')
        agent_script_dir = os.path.join(resources_dir, 'cloudify_agent')
        os.makedirs(agent_dir)
        os.makedirs(agent_script_dir)
        os.makedirs(os.path.join(self.temp_folder, 'cloudify'))

        agent_path = os.path.join(agent_dir, package_name)
        shutil.copyfile(agent_package.get_package_path(), agent_path)

        new_env = {
            constants.REST_HOST_KEY: 'localhost',
            constants.MANAGER_FILE_SERVER_URL_KEY:
                'http://localhost:{0}'.format(port),
            constants.MANAGER_FILE_SERVER_ROOT_KEY: resources_dir,
            constants.REST_PORT_KEY: str(port),
        }
        with patch.dict(os.environ, new_env):
            try:
                yield
            finally:
                fs.stop()

    @patch('cloudify_agent.installer.operations.delete_agent_rabbitmq_user')
    @patch('cloudify.agent_utils.get_rest_client',
           return_value=MockRestclient())
    @only_ci
    def test_install_new_agent(self, *_):
        agent_name = utils.internal.generate_agent_name()

        blueprint_path = resources.get_resource(
            'blueprints/install-new-agent/install-new-agent-blueprint.yaml')
        self.logger.info('Initiating local env')
        inputs = {
            'name': agent_name,
            'ssl_cert_path': self._rest_cert_path
        }

        # Necessary to patch this method, because by default port 80 is used
        def http_rest_host(cloudify_agent):
            return os.environ[constants.MANAGER_FILE_SERVER_URL_KEY]

        # Necessary to patch, because by default https will be used
        def file_server_url(*args, **kwargs):
            return '{0}/resources'.format(http_rest_host({}))

        # Need to patch, to avoid broker_ssl_enabled being True
        @contextmanager
        def get_amqp_client(agent):
            yield get_client()

        with self._manager_env():
            with patch('cloudify_agent.api.utils.get_manager_file_server_url',
                       file_server_url):
                env = local.init_env(name=self._testMethodName,
                                     blueprint_path=blueprint_path,
                                     inputs=inputs)
                with patch('cloudify_agent.operations._http_rest_host',
                           http_rest_host):
                    with patch('cloudify_agent.operations._get_amqp_client',
                               get_amqp_client):
                        env.execute('install', task_retries=0)
            agent_dict = self.get_agent_dict(env, 'new_agent_host')
            agent_ssl_cert.verify_remote_cert(agent_dict['agent_dir'])
            new_agent_name = agent_dict['name']
            self.assertNotEqual(new_agent_name, agent_name)
            self.assert_daemon_alive(new_agent_name)
            env.execute('uninstall', task_retries=1)
            self.wait_for_daemon_dead(name=agent_name)
            self.wait_for_daemon_dead(name=new_agent_name)


rest_mock = MagicMock()
rest_mock.manager = MagicMock()
rest_mock.manager.get_version = lambda: '3.3'


class TestCreateAgentAmqp(BaseTest, unittest.TestCase):
    @staticmethod
    @patch('cloudify_agent.installer.config.agent_config.ctx', mock_context())
    @patch('cloudify.utils.ctx', mock_context())
    def _create_agent():
        old_agent = CloudifyAgentConfig({
            'install_method': 'remote',
            'ip': '10.0.4.47',
            'rest_host': '10.0.4.46',
            'distro': 'ubuntu',
            'distro_codename': 'trusty',
            'basedir': '/home/vagrant',
            'user': 'vagrant',
            'key': '~/.ssh/id_rsa',
            'windows': False,
            'package_url': 'http://10.0.4.46:53229/packages/agents/'
                           'ubuntu-trusty-agent.tar.gz',
            'version': '4.4',
            'broker_config': {
                'broker_ip': '10.0.4.46',
                'broker_pass': 'test_pass',
                'broker_user': 'test_user',
                'broker_ssl_cert': ''
            }
        })

        old_agent.set_execution_params()
        old_agent.set_default_values()
        old_agent.set_installation_params(runner=None)
        return old_agent

    @contextmanager
    def _set_context(self, host='localhost'):
        old_context = ctx
        try:
            os.environ[constants.MANAGER_FILE_SERVER_ROOT_KEY] = \
                self.temp_folder

            properties = {}
            properties['cloudify_agent'] = self._create_agent()
            properties['agent_status'] = {'agent_alive_crossbroker': True}
            mock = mocks.MockCloudifyContext(
                node_id='host_af231',
                runtime_properties=properties,
                node_name='host',
                properties={'cloudify_agent': {}},
                bootstrap_context=context.BootstrapContext({
                    'cloudify_agent': {
                        'networks': {
                            'default': {
                                'manager': host,
                                'brokers': [host],
                            },
                        },
                    },
                })
            )
            current_ctx.set(mock)
            yield
        finally:
            current_ctx.set(old_context)

    def test_create_agent_dict(self):
        with self._set_context(host='10.0.4.48'):
            old_agent = self._create_agent()
            new_agent = operations.create_new_agent_config(old_agent)
            new_agent['version'] = '3.4'
            third_agent = operations.create_new_agent_config(new_agent)
            equal_keys = ['ip', 'basedir', 'user']
            for k in equal_keys:
                self.assertEqual(old_agent[k], new_agent[k])
                self.assertEqual(old_agent[k], third_agent[k])
            nonequal_keys = ['agent_dir', 'workdir', 'envdir', 'name',
                             'rest_host']
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
            agent = operations.create_new_agent_config(new_agent)
            self.assertIn(new_agent['name'], agent['name'])

    @patch('cloudify_agent.operations._send_amqp_task')
    @patch('cloudify_agent.api.utils.is_agent_alive',
           MagicMock(return_value=True))
    @patch('cloudify.agent_utils.get_rest_client',
           return_value=MockRestclient())
    def test_create_agent_from_old_agent(self, *mocks):
        with self._set_context():
            self._create_cloudify_agent_dir()
            old_name = ctx.instance.runtime_properties[
                'cloudify_agent']['name']
            old_agent_dir = ctx.instance.runtime_properties[
                'cloudify_agent']['agent_dir']
            old_queue = ctx.instance.runtime_properties[
                'cloudify_agent']['queue']

            operations.create_agent_amqp()
            new_name = ctx.instance.runtime_properties[
                'cloudify_agent']['name']
            new_agent_dir = ctx.instance.runtime_properties[
                'cloudify_agent']['agent_dir']
            new_queue = ctx.instance.runtime_properties[
                'cloudify_agent']['queue']
            self.assertNotEquals(old_name, new_name)
            self.assertNotEquals(old_agent_dir, new_agent_dir)
            self.assertNotEquals(old_queue, new_queue)

    def _create_cloudify_agent_dir(self):
        agent_script_dir = os.path.join(self.temp_folder, 'cloudify_agent')
        os.makedirs(agent_script_dir)
