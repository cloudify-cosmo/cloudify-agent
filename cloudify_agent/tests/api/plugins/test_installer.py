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

import tempfile
import logging
import os
import platform
from contextlib import contextmanager

from wagon import utils as wagon_utils
from mock import patch

from cloudify import constants
from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner
from cloudify.exceptions import NonRecoverableError
from cloudify.exceptions import CommandExecutionException
from cloudify_rest_client.plugins import Plugin

from cloudify_agent.api.plugins import installer
from cloudify_agent.api import utils
from cloudify_agent.api import exceptions

from cloudify_agent.tests import resources
from cloudify_agent.tests import utils as test_utils
from cloudify_agent.tests import BaseTest


class PluginInstallerTest(BaseTest):

    fs = None

    @classmethod
    def setUpClass(cls):

        cls.logger = setup_logger(cls.__name__, logger_level=logging.DEBUG)
        cls.runner = LocalCommandRunner(cls.logger)

        cls.file_server_resource_base = tempfile.mkdtemp(
            prefix='file-server-resource-base')
        cls.fs = test_utils.FileServer(
            root_path=cls.file_server_resource_base)
        cls.fs.start()
        cls.file_server_url = 'http://localhost:{0}'.format(cls.fs.port)

        cls.plugins_to_be_installed = [
            'mock-plugin',
            'mock-plugin-with-requirements'
        ]

        for plugin_dir in cls.plugins_to_be_installed:
            test_utils.create_plugin_tar(
                plugin_dir_name=plugin_dir,
                target_directory=cls.file_server_resource_base)

    def setUp(self):
        self.installer = installer.PluginInstaller(logger=self.logger)

    def tearDown(self):
        self.installer.uninstall('mock-plugin')
        self.installer.uninstall('TowelStuff')
        self.installer.uninstall('mock-plugin-with-requirements')

    @classmethod
    def tearDownClass(cls):
        cls.fs.stop()

    def _create_plugin_url(self, plugin_tar_name):
        return '{0}/{1}'.format(self.file_server_url, plugin_tar_name)

    def _plugin_struct(self, source, args=None):
        return {
            'source': self._create_plugin_url(source),
            'install_arguments': args
        }

    def _assert_plugin_installed(self, plugin_name, dependencies=None):
        if not dependencies:
            dependencies = []
        out = self.runner.run('{0} freeze'
                              .format(utils.get_pip_path())).std_out
        packages = []
        for line in out.splitlines():
            packages.append(line.split('==')[0])
        self.assertIn(plugin_name, out)
        for dependency in dependencies:
            self.assertIn(dependency, packages)

    def _assert_plugin_not_installed(self, plugin_name):
        out = self.runner.run('{0} freeze'
                              .format(utils.get_pip_path())).std_out
        packages = []
        for line in out.splitlines():
            packages.append(line.split('==')[0])
        self.assertNotIn(plugin_name, packages)

    def test_install(self):
        self.installer.install(self._plugin_struct(source='mock-plugin.tar'))
        self._assert_plugin_installed('mock-plugin')

    def test_install_with_requirements(self):
        self.installer.install(self._plugin_struct(
            source='mock-plugin-with-requirements.tar',
            args='-r requirements.txt'))
        self._assert_plugin_installed(
            plugin_name='mock-plugin-with-requirements',
            dependencies=['TowelStuff'])

    def test_uninstall(self):
        self.installer.install(self._plugin_struct(source='mock-plugin.tar'))
        self._assert_plugin_installed('mock-plugin')
        self.installer.uninstall('mock-plugin')
        self._assert_plugin_not_installed('mock-plugin')

    def test_uninstall_ignore_missing_false(self):
        self.assertRaises(CommandExecutionException,
                          self.installer.uninstall, 'missing-plugin', False)

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

        extracted_plugin_path = installer.extract_package_to_dir(
            plugin_tar_url)
        self.assertTrue(test_utils.are_dir_trees_equal(
            plugin_source_path,
            extracted_plugin_path))

    def test_extract_package_name(self):
        package_dir = os.path.join(resources.get_resource('plugins'),
                                   'mock-plugin')
        self.assertEqual(
            'mock-plugin',
            installer.extract_package_name(package_dir))


class PipVersionParserTestCase(BaseTest):

    def test_parse_long_format_version(self):
        version_tupple = installer.parse_pip_version('1.5.4')
        self.assertEqual(('1', '5', '4'), version_tupple)

    def test_parse_short_format_version(self):
        version_tupple = installer.parse_pip_version('6.0')
        self.assertEqual(('6', '0', ''), version_tupple)

    def test_pip6_not_higher(self):
        result = installer.is_pip6_or_higher('1.5.4')
        self.assertEqual(result, False)

    def test_pip6_exactly(self):
        result = installer.is_pip6_or_higher('6.0')
        self.assertEqual(result, True)

    def test_pip6_is_higher(self):
        result = installer.is_pip6_or_higher('6.0.6')
        self.assertEqual(result, True)

    def test_parse_invalid_major_version(self):
        expected_err_msg = 'Invalid pip version: "a.5.4", major version is ' \
                           '"a" while expected to be a number'
        self.assertRaisesRegex(
            exceptions.PluginInstallationError, expected_err_msg,
            installer.parse_pip_version, 'a.5.4')

    def test_parse_invalid_minor_version(self):
        expected_err_msg = 'Invalid pip version: "1.a.4", minor version is ' \
                           '"a" while expected to be a number'
        self.assertRaisesRegex(
            exceptions.PluginInstallationError, expected_err_msg,
            installer.parse_pip_version, '1.a.4')

    def test_parse_too_short_version(self):
        expected_err_msg = 'Unknown formatting of pip version: ' \
                           '"6", expected ' \
                           'dot-delimited numbers ' \
                           '\(e.g. "1.5.4", "6.0"\)'
        self.assertRaisesRegex(
            exceptions.PluginInstallationError, expected_err_msg,
            installer.parse_pip_version, '6')

    def test_parse_numeric_version(self):
        expected_err_msg = 'Invalid pip version: 6 is not a string'
        self.assertRaisesRegex(
            exceptions.PluginInstallationError, expected_err_msg,
            installer.parse_pip_version, 6)

    def test_parse_alpha_version(self):
        expected_err_msg = 'Unknown formatting of pip ' \
                           'version: "a", expected ' \
                           'dot-delimited ' \
                           'numbers \(e.g. "1.5.4", "6.0"\)'
        self.assertRaisesRegex(
            exceptions.PluginInstallationError, expected_err_msg,
            installer.parse_pip_version, 'a')

    def test_parse_wrong_obj(self):
        expected_err_msg = 'Invalid pip version: \[6\] is not a string'
        self.assertRaisesRegex(
            exceptions.PluginInstallationError, expected_err_msg,
            installer.parse_pip_version, [6])


class TestGetSourceAndGetArgs(BaseTest):

    def test_get_url_and_args_http_no_args(self):
        plugin = {'source': 'http://google.com'}
        url = installer.get_plugin_source(plugin)
        args = installer.get_plugin_args(plugin)
        self.assertEqual(url, 'http://google.com')
        self.assertEqual(args, '')

    def test_get_url_https(self):
        plugin = {
            'source': 'https://google.com',
            'install_arguments': '--pre'
        }
        url = installer.get_plugin_source(plugin)
        args = installer.get_plugin_args(plugin)

        self.assertEqual(url, 'https://google.com')
        self.assertEqual(args, '--pre')

    def test_get_url_faulty_schema(self):
        self.assertRaises(NonRecoverableError,
                          installer.get_plugin_source,
                          {'source': 'bla://google.com'})

    def test_get_plugin_source_from_blueprints_dir(self):
        plugin = {
            'source': 'plugin-dir-name'
        }
        with test_utils.env(
                constants.MANAGER_FILE_SERVER_BLUEPRINTS_ROOT_URL_KEY,
                'localhost'):
            source = installer.get_plugin_source(
                plugin,
                blueprint_id='blueprint_id')
        self.assertEqual(
            'localhost/blueprint_id/plugins/plugin-dir-name.zip',
            source)


class TestGetPluginID(BaseTest):

    def test_no_package_name(self):
        with self._patch(plugins=[]) as client:
            self.assertIsNone(installer.get_plugin_id(plugin={}))
            self.assertIsNone(client.plugins.kwargs)

    def test_no_managed_plugins(self):
        plugin = {'package_name': 'p'}
        with self._patch(plugins=[]) as client:
            self.assertIsNone(installer.get_plugin_id(plugin=plugin))
            self.assertEqual(plugin, client.plugins.kwargs)

    def test_last_version_selection(self):
        plugins = [
            {'id': '1', 'package_version': '1'},
            {'id': '2', 'package_version': '3.5a1'},
            {'id': '3', 'package_version': '2.2b1'},
            {'id': '4', 'package_version': '1.2c1'},
            {'id': '5', 'package_version': '3.4d2'},
        ]
        for p in plugins:
            p['supported_platform'] = 'any'
        plugin = {'package_name': 'plugin'}
        with self._patch(plugins=plugins):
            self.assertEquals('2', installer.get_plugin_id(plugin=plugin))

    def test_implicit_supported_platform(self):
        plugins = [
            {'id': '1'},
            {'id': '2'},
            {'id': '3',
             'supported_platform': wagon_utils.get_platform()},
            {'id': '4'},
            {'id': '5'},
        ]
        plugin = {'package_name': 'plugin', 'distribution': 'x',
                  'distribution_release': 'x'}
        with self._patch(plugins=plugins):
            self.assertEquals('3', installer.get_plugin_id(plugin=plugin))

    def test_implicit_dist_and_dist_release(self):
        if os.name == 'nt':
            self.skipTest('Linux only test')
        dist, _, dist_release = platform.linux_distribution(
            full_distribution_name=False)
        plugins = [
            {'id': '1'},
            {'id': '2'},
            {'id': '3'},
            {'id': '4',
             'distribution': dist, 'distribution_release': dist_release},
            {'id': '5'},
        ]
        plugin = {'package_name': 'plugin', 'supported_platform': 'x'}
        with self._patch(plugins=plugins):
            self.assertEquals('4', installer.get_plugin_id(plugin=plugin))

    def test_list_filter_query_builder(self):
        plugin1 = {'package_name': 'a'}
        plugin2 = {'package_name': 'a',
                   'package_version': 'b',
                   'distribution': 'c',
                   'distribution_version': 'd',
                   'distribution_release': 'e',
                   'supported_platform': 'f'}
        for plugin in [plugin1, plugin2]:
            with self._patch(plugins=[]) as client:
                installer.get_plugin_id(plugin)
                self.assertEqual(plugin, client.plugins.kwargs)

    @contextmanager
    def _patch(self, plugins):
        plugins = [Plugin(p) for p in plugins]
        client = TestGetPluginID.Client(plugins)
        get_rest_client = lambda: client
        with patch('cloudify_agent.api.plugins.installer.get_rest_client',
                   get_rest_client):
            yield client

    class Plugins(object):
        def __init__(self, plugins):
            self.plugins = plugins
            self.kwargs = None

        def list(self, **kwargs):
            self.kwargs = kwargs
            return self.plugins

    class Client(object):
        def __init__(self, plugins):
            self.plugins = TestGetPluginID.Plugins(plugins)
