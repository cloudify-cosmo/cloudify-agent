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
from mock import patch

from cloudify import constants
from cloudify_agent.api import utils
from cloudify_agent.installer.config import configuration
from cloudify_agent.tests import BaseTest
from cloudify_agent.tests.installer.config import mock_context


class TestConfiguration(BaseTest):

    @patch('cloudify_agent.installer.config.configuration.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.attributes.ctx',
           mock_context())
    @patch('cloudify.utils.ctx', mock_context())
    def test_prepare(self):

        cloudify_agent = {'local': True}
        configuration.prepare_connection(cloudify_agent)
        configuration.prepare_agent(cloudify_agent, None)

        user = getpass.getuser()
        basedir = utils.get_home_dir(user)
        agent_dir = os.path.join(basedir, 'test_deployment')
        envdir = os.path.join(agent_dir, 'env')
        workdir = os.path.join(agent_dir, 'work')

        # This test needs to be adapted to security settings
        expected = {
            'agent_dir': agent_dir,
            'process_management':
                {'name': 'init.d' if os.name == 'posix' else 'nssm'},
            'basedir': basedir,
            'name': 'test_deployment',
            'rest_host': 'localhost',
            'rest_port': 80,
            'rest_protocol': 'http',
            'file_server_host': 'localhost',
            'file_server_port': 53229,
            'file_server_protocol': 'http',
            'queue': 'test_deployment',
            'envdir': envdir,
            'user': user,
            'local': True,
            'disable_requiretty': True,
            'env': {},
            'fabric_env': {},
            'max_workers': 5,
            'min_workers': 0,
            'workdir': workdir,
            'agent_rest_cert_path': os.environ[constants.AGENT_REST_CERT_PATH],
            'broker_ssl_cert_path': os.environ[constants.BROKER_SSL_CERT_PATH],
            'windows': os.name == 'nt',
            'system_python': 'python',
            'remote_execution': True,
            'broker_get_settings_from_manager': True,
            'security_enabled': False,
            'rest_cert_content': '',
            'rest_username': None,
            'rest_password': None,
            'verify_rest_certificate': False,
            'bypass_maintenance_mode': False,
            'rest_token': None
        }
        if os.name == 'posix':
            distro = platform.dist()[0].lower()
            distro_codename = platform.dist()[2].lower()
            expected['distro'] = platform.dist()[0].lower()
            expected['distro_codename'] = platform.dist()[2].lower()
            expected['package_url'] = 'localhost/packages/agents/' \
                                      '{0}-{1}-agent.tar.gz'\
                .format(distro, distro_codename)
        else:
            expected['package_url'] = 'localhost/packages/agents/' \
                                      'cloudify-windows-agent.exe'

        self.maxDiff = None
        self.assertDictEqual(expected, cloudify_agent)

    @patch('cloudify_agent.installer.config.configuration.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.attributes.ctx',
           mock_context())
    @patch('cloudify.utils.ctx', mock_context())
    def test_prepare_secured(self):

        cloudify_agent = {'local': True, 'security_enabled': True,
                          'rest_protocol': 'https', 'rest_port': '443',
                          'rest_username': 'the_user',
                          'rest_password': 'the_pass',
                          'file_server_protocol': 'https',
                          'verify_rest_certificate': True,
                          'rest_cert_content': '--this_is-my-certificate--'}
        configuration.prepare_connection(cloudify_agent)
        configuration.prepare_agent(cloudify_agent, None)

        user = getpass.getuser()
        basedir = utils.get_home_dir(user)
        agent_dir = os.path.join(basedir, 'test_deployment')
        envdir = os.path.join(agent_dir, 'env')
        workdir = os.path.join(agent_dir, 'work')

        # This test needs to be adapted to security settings
        expected = {
            'agent_dir': agent_dir,
            'process_management':
                {'name': 'init.d' if os.name == 'posix' else 'nssm'},
            'basedir': basedir,
            'name': 'test_deployment',
            'rest_host': 'localhost',
            'rest_port': '443',
            'rest_protocol': 'https',
            'file_server_host': 'localhost',
            'file_server_port': 53229,
            'file_server_protocol': 'https',
            'queue': 'test_deployment',
            'envdir': envdir,
            'user': user,
            'local': True,
            'disable_requiretty': True,
            'env': {},
            'fabric_env': {},
            'max_workers': 5,
            'min_workers': 0,
            'workdir': workdir,
            'agent_rest_cert_path': os.environ[constants.AGENT_REST_CERT_PATH],
            'broker_ssl_cert_path': os.environ[constants.BROKER_SSL_CERT_PATH],
            'windows': os.name == 'nt',
            'system_python': 'python',
            'remote_execution': True,
            'broker_get_settings_from_manager': True,
            'security_enabled': True,
            'rest_cert_content': '--this_is-my-certificate--',
            'rest_username': 'the_user',
            'rest_password': 'the_pass',
            'verify_rest_certificate': True,
            'bypass_maintenance_mode': False,
            'rest_token': None
        }
        if os.name == 'posix':
            distro = platform.dist()[0].lower()
            distro_codename = platform.dist()[2].lower()
            expected['distro'] = platform.dist()[0].lower()
            expected['distro_codename'] = platform.dist()[2].lower()
            expected['package_url'] = 'localhost/packages/agents/' \
                                      '{0}-{1}-agent.tar.gz' \
                .format(distro, distro_codename)
        else:
            expected['package_url'] = 'localhost/packages/agents/' \
                                      'cloudify-windows-agent.exe'

        self.maxDiff = None
        self.assertDictEqual(expected, cloudify_agent)
