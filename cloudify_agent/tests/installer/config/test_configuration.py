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

    def setUp(self):
        super(TestConfiguration, self).setUp()
        os.environ[constants.MANAGER_FILE_SERVER_URL_KEY] = 'localhost'
        os.environ[constants.MANAGER_IP_KEY] = 'localhost'

    def tearDown(self):
        del os.environ[constants.MANAGER_FILE_SERVER_URL_KEY]
        del os.environ[constants.MANAGER_IP_KEY]

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

        user = getpass.getuser()
        basedir = utils.get_home_dir(user)
        agent_dir = os.path.join(basedir, 'test_deployment')
        envdir = os.path.join(agent_dir, 'env')
        workdir = os.path.join(agent_dir, 'work')
        expected = {
            'agent_dir': agent_dir,
            'process_management':
                {'name': 'init.d' if os.name == 'posix' else 'nssm'},
            'basedir': basedir,
            'name': 'test_deployment',
            'manager_ip': 'localhost',
            'manager_port': 8101,
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
            'windows': os.name == 'nt',
            'system_python': 'python',
            'remote_execution': True,
            'broker_get_settings_from_manager': True,
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
