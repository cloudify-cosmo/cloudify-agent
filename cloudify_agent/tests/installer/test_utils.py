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

from mock import patch, MagicMock

from cloudify_agent.installer import utils, LocalInstallerMixin
from cloudify_agent.tests import BaseTest
from cloudify_agent.tests.api.pm import only_os
from cloudify_agent.api.utils import get_all_private_ips


class TestUtils(BaseTest):

    def test_env_to_file(self):
        file_path = utils.env_to_file({'key': 'value', 'key2': 'value2'})
        with open(file_path) as f:
            content = f.read()
        self.assertIn('export key=value', content)
        self.assertIn('export key2=value2', content)

    def test_env_to_file_nt(self):
        file_path = utils.env_to_file({'key': 'value', 'key2': 'value2'},
                                      posix=False)
        with open(file_path) as f:
            content = f.read()
        self.assertIn('set key=value', content)
        self.assertIn('set key2=value2', content)

    def test_stringify_values(self):

        env = {
            'key': 'string-value',
            'key2': 5,
            'dict-key': {
                'key3': 10
            }
        }

        stringified = utils.stringify_values(dictionary=env)
        self.assertEqual(stringified['key'], 'string-value')
        self.assertEqual(stringified['key2'], '5')
        self.assertEqual(stringified['dict-key']['key3'], '10')

    def test_purge_none_values(self):

        dictionary = {
            'key': 'value',
            'key2': None
        }

        purged = utils.purge_none_values(dictionary)
        self.assertEqual(purged['key'], 'value')
        self.assertNotIn('key2', purged)

    @only_os('posix')
    def test_manager_ip_selection(self):
        agent_installer = LocalInstallerMixin({})
        # This will throw an error if none of the addresses will work
        ip = agent_installer._calculate_manager_ip(22)
        self.logger.info('Calculated IP: {0}'.format(ip))

    @only_os('posix')
    def test_manager_ip_selection_with_extra_ips(self):
        agent_installer = LocalInstallerMixin({})
        all_ips = get_all_private_ips()
        all_ips.insert(0, '254.254.254.254')
        all_ips.append('172.20.0.2')
        with patch('cloudify_agent.api.utils.get_all_private_ips',
                   MagicMock(return_value=all_ips)):
            # This will throw an error if none of the addresses will work
            ip = agent_installer._calculate_manager_ip(22)
        self.logger.info('Calculated IP: {0}'.format(ip))
