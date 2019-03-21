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

import getpass
import os
import platform
import unittest
from mock import patch

from cloudify import constants
from cloudify_agent.api import utils
from cloudify_agent.installer.config.agent_config import CloudifyAgentConfig
from cloudify_agent.tests import BaseTest
from cloudify_agent.tests.installer.config import mock_context


class TestConfiguration(BaseTest, unittest.TestCase):
    def setUp(self):
        super(TestConfiguration, self).setUp()

    def test_prepare(self):
        expected = self._get_distro_package_url(rest_port=80)
        expected['rest_port'] = 80

        self._test_prepare(
            agent_config={'local': True},
            expected_values=expected
        )

    def test_prepare_secured(self):
        expected = self._get_distro_package_url(rest_port=443)
        expected['rest_port'] = '443'

        self._test_prepare(
            agent_config={'local': True, 'rest_port': '443'},
            expected_values=expected
        )

    def test_prepare_multi_networks(self):
        manager_host = '10.0.0.1'
        network_name = 'test_network'
        expected = self._get_distro_package_url(
            rest_port=80, manager_host=manager_host
        )
        expected['rest_port'] = 80
        expected['rest_host'] = manager_host
        expected['broker_ip'] = [manager_host]
        expected['network'] = 'test_network'

        self._test_prepare(
            agent_config={
                'local': True,
                'networks': {
                    'default': {
                        'manager': 'localhost',
                        'brokers': ['localhost'],
                    },
                    network_name: {
                        'manager': manager_host,
                        'brokers': [manager_host],
                    },
                },
                'network': network_name
            },
            expected_values=expected
        )

    @staticmethod
    def _get_distro_package_url(rest_port, manager_host='localhost'):
        result = {}
        base_url = utils.get_manager_file_server_url(manager_host, rest_port)
        agent_package_url = '{0}/packages/agents'.format(base_url)
        if os.name == 'posix':
            distro = platform.dist()[0].lower()
            distro_codename = platform.dist()[2].lower()
            result['distro'] = platform.dist()[0].lower()
            result['distro_codename'] = platform.dist()[2].lower()
            package = '{0}-{1}-agent.tar.gz'.format(distro, distro_codename)
        else:
            package = 'cloudify-windows-agent.exe'
        result['package_url'] = '{0}/{1}'.format(agent_package_url, package)
        return result

    @patch('cloudify_agent.installer.config.agent_config.ctx',
           mock_context(
               agent_runtime_properties={'extra': {
                   'ssl_cert_path': '/tmp/blabla',
               }}
           ))
    def test_connection_params_propagation(self):
        # Testing that if a connection timeout is passed as an agent runtime
        # property, it would be propagated to the cloudify agent dict
        cloudify_agent = CloudifyAgentConfig()
        cloudify_agent.set_initial_values(True, agent_config={'local': True})
        self.assertEqual(cloudify_agent['ssl_cert_path'], '/tmp/blabla')

    @patch('cloudify_agent.installer.config.agent_config.ctx', mock_context())
    @patch('cloudify.utils.ctx', mock_context())
    def _test_prepare(self, agent_config, expected_values):
        cloudify_agent = CloudifyAgentConfig()
        cloudify_agent.set_initial_values(True, agent_config=agent_config)
        cloudify_agent.set_execution_params()
        cloudify_agent.set_default_values()
        cloudify_agent.set_installation_params(None)

        user = getpass.getuser()
        basedir = utils.get_home_dir(user)
        agent_dir = os.path.join(basedir, 'test_deployment')
        envdir = os.path.join(agent_dir, 'env')
        workdir = os.path.join(agent_dir, 'work')

        # This test needs to be adapted to security settings
        expected = {
            'agent_dir': agent_dir,
            'process_management': {
                'name': 'init.d' if os.name == 'posix' else 'nssm'
            },
            'basedir': basedir,
            'name': 'test_deployment',
            'rest_host': 'localhost',
            'broker_ip': ['localhost'],
            'broker_ssl_cert': '',
            'heartbeat': None,
            'queue': 'test_deployment',
            'envdir': envdir,
            'user': user,
            'local': True,
            'install_method': 'local',
            'disable_requiretty': True,
            'env': {},
            'fabric_env': {},
            'max_workers': 20,
            'min_workers': 0,
            'workdir': workdir,
            'broker_ssl_cert_path': os.environ[constants.BROKER_SSL_CERT_PATH],
            'windows': os.name == 'nt',
            'system_python': 'python',
            'bypass_maintenance': False,
            'network': 'default',
            'version': utils.get_agent_version(),
            'node_instance_id': 'test_node'
        }
        expected.update(expected_values)

        self.maxDiff = None
        self.assertDictEqual(expected, cloudify_agent)
