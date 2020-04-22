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
from contextlib import contextmanager

from mock import patch, MagicMock
from testtools import TestCase

from cloudify import constants
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
from cloudify_agent.tests.installer.config import (
    mock_context,
    get_tenant_mock
)
from cloudify_agent.tests.utils import FileServer

from cloudify_agent.tests.api.pm import BaseDaemonLiveTestCase
from cloudify_agent.tests.api.pm import only_ci, only_os
from cloudify_rest_client.manager import ManagerItem


class TestInstallNewAgent(BaseDaemonLiveTestCase, TestCase):
    @contextmanager
    def _manager_env(self):
        port = 8756
        fs = FileServer(root_path=self.temp_folder, port=port)
        fs.start()
        self.addCleanup(fs.stop)
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
        self.addCleanup(agent_package.cleanup)

        new_env = {
            constants.MANAGER_FILE_SERVER_ROOT_KEY: resources_dir,
            constants.REST_PORT_KEY: str(port),
            constants.MANAGER_NAME: 'cloudify'
        }

        original_create_op_context = operations._get_cloudify_context

        def mock_create_op_context(agent,
                                   task_name,
                                   new_agent_connection=None):
            context = original_create_op_context(
                agent,
                task_name,
                new_agent_connection=new_agent_connection
            )
            context['__cloudify_context']['local'] = True
            return context

        # Need to patch, to avoid broker_ssl_enabled being True
        @contextmanager
        def get_amqp_client(agent):
            yield get_client()

        managers = [
            ManagerItem({
                'networks': {'default': '127.0.0.1'},
                'ca_cert_content': agent_ssl_cert.DUMMY_CERT,
                'hostname': 'cloudify'
            })
        ]
        patches = [
            patch.dict(os.environ, new_env),
            patch('cloudify_agent.operations._get_amqp_client',
                  get_amqp_client),
            patch('cloudify.endpoint.LocalEndpoint.get_managers',
                  return_value=managers),
            patch('cloudify_agent.operations._get_cloudify_context',
                  mock_create_op_context),
            get_tenant_mock()
        ]
        for p in patches:
            p.start()
        try:
            yield
        finally:
            for p in patches:
                p.stop()
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

        with self._manager_env():
            env = local.init_env(name=self._testMethodName,
                                 blueprint_path=blueprint_path,
                                 inputs=inputs)
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


@only_os('posix')
class TestCreateAgentAmqp(BaseTest, TestCase):
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
            os.environ[constants.MANAGER_NAME] = 'cloudify'
            properties = {}
            properties['cloudify_agent'] = self._create_agent()
            properties['agent_status'] = {'agent_alive_crossbroker': True}
            mock = mocks.MockCloudifyContext(
                node_id='host_af231',
                runtime_properties=properties,
                node_name='host',
                properties={'cloudify_agent': {}},
                brokers=[{
                    'networks': {'default': host}
                }],
                managers=[{
                    'networks': {'default': host},
                    'hostname': 'cloudify'
                }]
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
            self.assertNotEqual(old_name, new_name)
            self.assertNotEqual(old_agent_dir, new_agent_dir)
            self.assertNotEqual(old_queue, new_queue)

    def _create_cloudify_agent_dir(self):
        agent_script_dir = os.path.join(self.temp_folder, 'cloudify_agent')
        os.makedirs(agent_script_dir)
