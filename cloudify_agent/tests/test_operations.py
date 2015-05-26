#########
# Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
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

from cloudify import constants

from cloudify.exceptions import NonRecoverableError
from cloudify_agent import operations

from cloudify_agent.tests import utils
from cloudify_agent.tests import BaseTest


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
