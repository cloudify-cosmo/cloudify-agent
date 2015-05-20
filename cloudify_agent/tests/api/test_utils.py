#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
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

import json
import os
import tempfile

from cloudify.utils import setup_logger
from cloudify.exceptions import NonRecoverableError

import cloudify_agent
from cloudify_agent.api import utils

from cloudify_agent.tests.api.pm import only_ci
from cloudify_agent.tests.api.pm import only_os
from cloudify_agent.tests import resources
from cloudify_agent.tests import utils as test_utils
from cloudify_agent.api import defaults
from cloudify_agent.api.pm.base import Daemon
from cloudify_agent.tests import BaseTest


class TestUtils(BaseTest):

    fs = None

    @classmethod
    def setUpClass(cls):
        cls.logger = setup_logger('cloudify_agent.tests.api.test_utils')
        cls.file_server_resource_base = tempfile.mkdtemp(
            prefix='file-server-resource-base')
        cls.fs = test_utils.FileServer(
            root_path=cls.file_server_resource_base)
        cls.fs.start()
        cls.file_server_url = 'http://localhost:{0}'.format(cls.fs.port)

    @classmethod
    def tearDownClass(cls):
        cls.fs.stop()

    def test_get_full_resource_path(self):
        full_path = utils.get_full_resource_path(
            os.path.join('pm', 'nssm', 'nssm.exe'))
        expected = os.path.join(
            os.path.dirname(cloudify_agent.__file__),
            'resources',
            'pm',
            'nssm',
            'nssm.exe')
        self.assertEqual(expected, full_path)

    def test_daemon_to_dict(self):

        daemon = Daemon(manager_ip='127.0.01')
        daemon_json = utils.daemon_to_dict(daemon)
        self.logger.info(json.dumps(daemon_json, indent=2))

    def test_get_resource(self):
        resource = utils.get_resource('pm/initd/initd.conf.template')
        path_to_resource = os.path.join(
            os.path.dirname(cloudify_agent.__file__),
            'resources',
            'pm',
            'initd',
            'initd.conf.template'
        )
        with open(path_to_resource) as f:
            self.assertEqual(f.read(), resource)

    def test_rendered_template_to_file(self):
        temp = utils.render_template_to_file(
            template_path='pm/initd/initd.conf.template',
            manager_ip='127.0.0.1'
        )
        with open(temp) as f:
            rendered = f.read()
            self.assertTrue('export MANAGEMENT_IP=127.0.0.1' in rendered)

    def test_resource_to_tempfile(self):
        temp = utils.resource_to_tempfile(
            resource_path='pm/initd/initd.conf.template'
        )
        path_to_resource = os.path.join(
            os.path.dirname(cloudify_agent.__file__),
            'resources',
            'pm',
            'initd',
            'initd.conf.template'
        )
        with open(path_to_resource) as expected:
            with open(temp) as actual:
                self.assertEqual('{0}{1}'.format(expected.read(),
                                                 os.linesep),
                                 actual.read())

    def test_content_to_tempfile(self):
        temp = utils.content_to_file(
            content='content'
        )
        with open(temp) as f:
            self.assertEqual('content{0}'
                             .format(os.linesep),
                             f.read())

    @only_ci
    @only_os('posix')
    def test_disable_requiretty(self):
        utils.disable_requiretty()

    @only_ci
    @only_os('posix')
    def test_fix_virtualenv(self):
        utils.fix_virtualenv()

    def test_generate_agent_name(self):
        name = utils.generate_agent_name()
        self.assertIn(defaults.CLOUDIFY_AGENT_PREFIX, name)

    def test_extract_package_to_dir(self):

        # create a plugin tar file and put it in the file server
        plugin_dir_name = 'mock-plugin-with-requirements'
        plugin_tar_name = test_utils.create_plugin_tar(
            plugin_dir_name,
            self.file_server_resource_base)

        plugin_source_path = resources.get_resource(os.path.join(
            'plugins', plugin_dir_name))
        plugin_tar_url = '{0}/{1}'.format(self.file_server_url,
                                          plugin_tar_name)

        extracted_plugin_path = utils.extract_package_to_dir(plugin_tar_url)
        self.assertTrue(test_utils.are_dir_trees_equal(
            plugin_source_path,
            extracted_plugin_path))

    def test_extract_package_name(self):
        package_dir = os.path.join(resources.get_resource('plugins'),
                                   'mock-plugin')
        self.assertEqual(
            'mock-plugin',
            utils.extract_package_name(package_dir))

    def test_dict_to_options(self):
        options_string = utils.dict_to_options(
            {'key': 'value',
             'key2': 'value2',
             'complex_key': 'complex_value'})

        expected = set(['--key2=value2', '--complex-key=complex_value',
                        '--key=value'])
        self.assertEqual(expected, set(options_string.split()))


class PipVersionParserTestCase(BaseTest):

    def test_parse_long_format_version(self):
        version_tupple = utils.parse_pip_version('1.5.4')
        self.assertEqual(('1', '5', '4'), version_tupple)

    def test_parse_short_format_version(self):
        version_tupple = utils.parse_pip_version('6.0')
        self.assertEqual(('6', '0', ''), version_tupple)

    def test_pip6_not_higher(self):
        result = utils.is_pip6_or_higher('1.5.4')
        self.assertEqual(result, False)

    def test_pip6_exactly(self):
        result = utils.is_pip6_or_higher('6.0')
        self.assertEqual(result, True)

    def test_pip6_is_higher(self):
        result = utils.is_pip6_or_higher('6.0.6')
        self.assertEqual(result, True)

    def test_parse_invalid_major_version(self):
        expected_err_msg = 'Invalid pip version: "a.5.4", major version is ' \
                           '"a" while expected to be a number'
        self.assertRaisesRegex(NonRecoverableError, expected_err_msg,
                               utils.parse_pip_version, 'a.5.4')

    def test_parse_invalid_minor_version(self):
        expected_err_msg = 'Invalid pip version: "1.a.4", minor version is ' \
                           '"a" while expected to be a number'
        self.assertRaisesRegex(NonRecoverableError, expected_err_msg,
                               utils.parse_pip_version, '1.a.4')

    def test_parse_too_short_version(self):
        expected_err_msg = 'Unknown formatting of pip version: ' \
                           '"6", expected ' \
                           'dot-delimited numbers ' \
                           '\(e.g. "1.5.4", "6.0"\)'
        self.assertRaisesRegex(NonRecoverableError, expected_err_msg,
                               utils.parse_pip_version, '6')

    def test_parse_numeric_version(self):
        expected_err_msg = 'Invalid pip version: 6 is not a string'
        self.assertRaisesRegex(NonRecoverableError, expected_err_msg,
                               utils.parse_pip_version, 6)

    def test_parse_alpha_version(self):
        expected_err_msg = 'Unknown formatting of pip ' \
                           'version: "a", expected ' \
                           'dot-delimited ' \
                           'numbers \(e.g. "1.5.4", "6.0"\)'
        self.assertRaisesRegex(NonRecoverableError, expected_err_msg,
                               utils.parse_pip_version, 'a')

    def test_parse_wrong_obj(self):
        expected_err_msg = 'Invalid pip version: \[6\] is not a string'
        self.assertRaisesRegex(NonRecoverableError, expected_err_msg,
                               utils.parse_pip_version, [6])
