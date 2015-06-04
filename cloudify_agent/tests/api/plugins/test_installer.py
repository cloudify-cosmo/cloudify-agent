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

from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner
from cloudify.exceptions import CommandExecutionException

from cloudify_agent.api.plugins.installer import PluginInstaller
from cloudify_agent.api import utils

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
        self.installer = PluginInstaller(logger=self.logger)

    def tearDown(self):
        self.installer.uninstall('mock-plugin')
        self.installer.uninstall('TowelStuff')
        self.installer.uninstall('mock-plugin-with-requirements')

    @classmethod
    def tearDownClass(cls):
        cls.fs.stop()

    def _create_plugin_url(self, plugin_tar_name):
        return '{0}/{1}'.format(self.file_server_url, plugin_tar_name)

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
        self.installer.install(self._create_plugin_url('mock-plugin.tar'))
        self._assert_plugin_installed('mock-plugin')

    def test_install_with_requirements(self):
        self.installer.install(self._create_plugin_url(
            'mock-plugin-with-requirements.tar'),
            '-r requirements.txt')
        self._assert_plugin_installed(
            plugin_name='mock-plugin-with-requirements',
            dependencies=['TowelStuff'])

    def test_uninstall(self):
        self.installer.install(self._create_plugin_url('mock-plugin.tar'))
        self._assert_plugin_installed('mock-plugin')
        self.installer.uninstall('mock-plugin')
        self._assert_plugin_not_installed('mock-plugin')

    def test_uninstall_ignore_missing_false(self):
        self.assertRaises(CommandExecutionException,
                          self.installer.uninstall, 'missing-plugin', False)
