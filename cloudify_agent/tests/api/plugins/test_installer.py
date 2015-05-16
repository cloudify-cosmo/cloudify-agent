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

import tempfile
import logging
from mock import patch

from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner

from cloudify_agent.api.plugins.installer import PluginInstaller
from cloudify_agent import VIRTUALENV
from cloudify_agent.tests import file_server
from cloudify_agent.tests import utils as test_utils
from cloudify_agent.tests import BaseTest
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.get_storage_directory',
       get_storage_directory)
class PluginInstallerTest(BaseTest):

    fs = None

    @classmethod
    def setUpClass(cls):

        cls.logger = setup_logger(
            'cloudify-agent.tests.api.plugins.test_installer',
            logger_level=logging.DEBUG)
        cls.runner = LocalCommandRunner(cls.logger)

        cls.file_server_resource_base = tempfile.mkdtemp(
            prefix='file-server-resource-base')
        cls.fs = file_server.FileServer(
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

        cls.installer = PluginInstaller(logger=cls.logger)

    @classmethod
    def tearDownClass(cls):
        cls.fs.stop()

    def _create_plugin_url(self, plugin_tar_name):
        return '{0}/{1}'.format(self.file_server_url, plugin_tar_name)

    def _assert_plugin_installed(self, plugin_name, dependencies=None):
        if not dependencies:
            dependencies = []
        out = self.runner.run('{0}/bin/pip list'.format(VIRTUALENV)).output
        self.assertIn(plugin_name, out)
        for dependency in dependencies:
            self.assertIn(dependency, out)

    def _uninstall_package_if_exists(self, plugin_name):
        out = self.runner.run('{0}/bin/pip list'.format(VIRTUALENV)).output
        if plugin_name in out:
            self.runner.run('{0}/bin/pip uninstall -y {1}'.format(
                VIRTUALENV, plugin_name), stdout_pipe=False)

    def test_install(self):
        try:
            self.installer.install(self._create_plugin_url('mock-plugin.tar'))
            self._assert_plugin_installed('mock-plugin')
        finally:
            self._uninstall_package_if_exists('mock-plugin')

    def test_install_with_requirements(self):

        try:
            self.installer.install(
                self._create_plugin_url(
                    'mock-plugin-with-requirements.tar'),
                '-r requirements.txt')
            self._assert_plugin_installed(
                plugin_name='mock-plugin-with-requirements',
                dependencies=['TowelStuff'])
        finally:
            self._uninstall_package_if_exists(
                'mock-plugin-with-requirements')

            #############################################################
            # TowelStuff is a sample package inside PyPi, it doesn't do
            # anything. we use it to test requirement files support
            #############################################################
            self._uninstall_package_if_exists(
                'TowelStuff')
