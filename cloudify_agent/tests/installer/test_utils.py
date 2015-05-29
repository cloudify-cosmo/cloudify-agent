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


from cloudify_agent.installer import utils

from cloudify_agent.tests import BaseTest


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
