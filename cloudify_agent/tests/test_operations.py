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
import urllib

from contextlib import contextmanager

from mock import patch, MagicMock

from cloudify import constants
from cloudify import context
from cloudify import ctx
from cloudify import mocks

from cloudify.state import current_ctx
from cloudify.workflows import local

from cloudify_agent import operations
from cloudify_agent.api import utils
from cloudify_agent.installer.config import configuration

from cloudify_agent.tests import BaseTest, resources, agent_package
from cloudify_agent.tests.installer.config import mock_context
from cloudify_agent.tests.utils import FileServer

from cloudify_agent.tests.api.pm import BaseDaemonLiveTestCase
from cloudify_agent.tests.api.pm import only_ci


_INSTALL_SCRIPT_URL = ('https://raw.githubusercontent.com/cloudify-cosmo/'
                       'cloudify-manager/master/resources/'
                       'rest-service/cloudify/install_agent.py')


class _MockManagerClient(object):
    def get_version(self):
        return {'version': '3.4'}


class _MockRestclient(object):
    @property
    def manager(self):
        return _MockManagerClient()


class TestInstallNewAgent(BaseDaemonLiveTestCase):

    @contextmanager
    def _manager_env(self):
        port = 8756
        fs = FileServer(
            root_path=self.temp_folder, port=port)
        fs.start()
        if os.name == 'nt':
            package_name = 'cloudify-windows-agent.exe'
        else:
            dist = platform.dist()
            package_name = '{0}-{1}-agent.tar.gz'.format(dist[0].lower(),
                                                         dist[2].lower())
        agent_dir = os.path.join(self.temp_folder, 'packages', 'agents')
        os.makedirs(agent_dir)
        agent_path = os.path.join(agent_dir, package_name)
        shutil.copyfile(agent_package.get_package_path(), agent_path)
        resources_dir = os.path.join(self.temp_folder, 'cloudify')
        os.makedirs(resources_dir)
        if os.getenv('AGENT_INSTALL_SCRIPT'):
            install_script_url = os.getenv('AGENT_INSTALL_SCRIPT')
        else:
            install_script_url = _INSTALL_SCRIPT_URL
        urllib.urlretrieve(install_script_url,
                           os.path.join(resources_dir, 'install_agent.py'))
        new_env = {
            constants.MANAGER_IP_KEY: 'localhost',
            constants.MANAGER_FILE_SERVER_URL_KEY:
                'http://localhost:{0}'.format(port)
        }
        with patch.dict(os.environ, new_env):
            try:
                yield
            finally:
                fs.stop()

    @patch('cloudify.manager.get_rest_client', _MockRestclient)
    @only_ci
    def test_install_new_agent(self):
        agent_name = utils.internal.generate_agent_name()

        blueprint_path = resources.get_resource(
            'blueprints/install-new-agent/install-new-agent-blueprint.yaml')
        self.logger.info('Initiating local env')
        inputs = {
            'name': agent_name,
        }
        with self._manager_env():
            env = local.init_env(name=self._testMethodName,
                                 blueprint_path=blueprint_path,
                                 inputs=inputs)
            env.execute('install', task_retries=0)
            self.assert_daemon_alive(name=agent_name)
            node_instances = env.storage.get_node_instances()
            new_agent_host = [n for n in node_instances
                              if n['name'] == 'new_agent_host'][0]
            new_agent_name = new_agent_host['runtime_properties'][
                'cloudify_agent']['name']
            self.assertNotEqual(new_agent_name, agent_name)
            self.assert_daemon_alive(name=new_agent_name)
            env.execute('uninstall', task_retries=1)
            self.wait_for_daemon_dead(name=agent_name)
            self.wait_for_daemon_dead(name=new_agent_name)


def _get_celery_mock():
    task_mock = MagicMock()

    class AgentKeeper:

        def set_value(self, task, kwargs, **_):
            self.agent = kwargs['cloudify_agent']
            return task_mock

        def get_value(self, *_, **__):
            return self.agent

    keeper = AgentKeeper()
    task_mock.get = keeper.get_value
    celery_mock = MagicMock()
    celery_mock.send_task = keeper.set_value
    return MagicMock(return_value=celery_mock)

rest_mock = MagicMock()
rest_mock.manager = MagicMock()
rest_mock.manager.get_version = lambda: '3.3'


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
            'package_url': 'http://10.0.4.46:53229/packages/agents/'
                           'ubuntu-trusty-agent.tar.gz',
            'version': '3.4',
            'broker_config': {
                'broker_ip': '10.0.4.46',
                'broker_pass': 'test_pass',
                'broker_user': 'test_user',
                'broker_port': '5672',
                'broker_ssl_enable': False,
                'broker_ssl_cert': ''
            }
        }
        configuration.prepare_connection(old_agent)
        configuration.prepare_agent(old_agent, None)
        return old_agent

    def _create_node_instance_context(self):
        properties = {}
        properties['cloudify_agent'] = self._create_agent()
        properties['agent_status'] = {'agent_alive_crossbroker': True}
        mock = mocks.MockCloudifyContext(
            node_id='host_af231',
            runtime_properties=properties,
            node_name='host',
            properties={'cloudify_agent': {}},
            bootstrap_context=context.BootstrapContext({
                'cloudify_agent': {}}))
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
            new_agent['version'] = '3.4'
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

    @patch('cloudify_agent.operations.celery.Celery', _get_celery_mock())
    @patch('cloudify_agent.operations.app', MagicMock())
    @patch('cloudify_agent.api.utils.get_agent_registered',
           MagicMock(return_value={'cloudify.dispatch.dispatch': {}}))
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
