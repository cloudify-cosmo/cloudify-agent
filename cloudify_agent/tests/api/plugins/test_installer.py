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
import shutil
import multiprocessing
from contextlib import contextmanager

from wagon import utils as wagon_utils
from mock import patch

from cloudify import constants
from cloudify import dispatch
from cloudify import exceptions as cloudify_exceptions
from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner
from cloudify.exceptions import NonRecoverableError
from cloudify_rest_client.plugins import Plugin

from cloudify_agent.api import exceptions
from cloudify_agent.api.plugins import installer

from cloudify_agent.tests import resources
from cloudify_agent.tests import utils as test_utils
from cloudify_agent.tests import BaseTest
from cloudify_agent.tests.api.pm import only_os


PLUGIN_NAME = 'plugin'
PACKAGE_NAME = 'mock-plugin'
PACKAGE_VERSION = '1.0'


class PluginInstallerTest(BaseTest):

    fs = None
    file_server_resource_base = None
    plugins_work_dir = None

    @classmethod
    def setUpClass(cls):

        cls.logger = setup_logger(cls.__name__, logger_level=logging.DEBUG)
        cls.runner = LocalCommandRunner(cls.logger)

        cls.plugins_work_dir = tempfile.mkdtemp(
            prefix='plugins-work-dir-')
        cls.file_server_resource_base = tempfile.mkdtemp(
            prefix='file-server-resource-base-')
        cls.fs = test_utils.FileServer(
            root_path=cls.file_server_resource_base)
        cls.fs.start()
        cls.file_server_url = 'http://localhost:{0}'.format(cls.fs.port)

        cls.plugins_to_be_installed = [
            'mock-plugin',
            'mock-plugin-modified',
            'mock-plugin-with-requirements'
        ]

        cls.wagons = {}

        for plugin_dir in cls.plugins_to_be_installed:
            test_utils.create_plugin_tar(
                plugin_dir_name=plugin_dir,
                target_directory=cls.file_server_resource_base)
            cls.wagons[plugin_dir] = test_utils.create_plugin_wagon(
                plugin_dir_name=plugin_dir,
                target_directory=cls.file_server_resource_base)

    def setUp(self):
        self.installer = installer.PluginInstaller(logger=self.logger)

    def tearDown(self):
        self.installer.uninstall(plugin=self._plugin_struct(''))
        self.installer.uninstall(plugin=self._plugin_struct(''),
                                 deployment_id='deployment')
        self.installer.uninstall_wagon(PACKAGE_NAME, PACKAGE_VERSION)

    @classmethod
    def tearDownClass(cls):
        cls.fs.stop()
        shutil.rmtree(cls.file_server_resource_base, ignore_errors=True)
        shutil.rmtree(cls.plugins_work_dir, ignore_errors=True)

    def _create_plugin_url(self, plugin_tar_name):
        return '{0}/{1}'.format(self.file_server_url, plugin_tar_name)

    def _plugin_struct(self, source=None, args=None, name=PLUGIN_NAME,
                       executor=None):
        return {
            'source': self._create_plugin_url(source) if source else None,
            'install_arguments': args,
            'name': name,
            'executor': executor
        }

    def _assert_task_runnable(self, task_name,
                              expected_return=None,
                              package_name=None,
                              package_version=None,
                              deployment_id=None):
        self.assertEqual(
            dispatch.dispatch(test_utils.op_context(
                task_name,
                plugin_name=PLUGIN_NAME,
                package_name=package_name,
                package_version=package_version,
                deployment_id=deployment_id)),
            expected_return)

    def _assert_task_not_runnable(self, task_name,
                                  deployment_id=None,
                                  package_name=None,
                                  package_version=None):
        self.assertRaises(
            cloudify_exceptions.NonRecoverableError,
            dispatch.dispatch,
            test_utils.op_context(task_name,
                                  plugin_name=PLUGIN_NAME,
                                  deployment_id=deployment_id,
                                  package_name=package_name,
                                  package_version=package_version))

    def test_install_from_source(self):
        self.installer.install(self._plugin_struct(source='mock-plugin.tar'))
        self._assert_task_runnable('mock_plugin.tasks.run',
                                   expected_return='run')
        self._assert_task_runnable('mock_plugin.tasks.call_entry_point',
                                   expected_return='mock-plugin-entry-point')

    def test_install_from_source_with_deployment_id(self):
        deployment_id = 'deployment'
        self.installer.install(self._plugin_struct(source='mock-plugin.tar'),
                               deployment_id=deployment_id)
        self._assert_task_not_runnable('mock_plugin.tasks.run')
        self._assert_task_runnable('mock_plugin.tasks.run',
                                   expected_return='run',
                                   deployment_id=deployment_id)

    def test_install_from_source_with_requirements(self):
        self.installer.install(self._plugin_struct(
            source='mock-plugin-with-requirements.tar',
            args='-r requirements.txt'))
        self._assert_task_runnable(
            'mock_with_install_args_for_test.module.do_stuff',
            expected_return='on the brilliant marble-sanded beaches of '
                            'Santraginus V')

    def test_install_from_source_already_exists(self):
        self.installer.install(self._plugin_struct(source='mock-plugin.tar'))
        with self.assertRaises(exceptions.PluginInstallationError) as c:
            self.installer.install(
                self._plugin_struct(source='mock-plugin.tar'))
        self.assertIn('already exists', str(c.exception))

    def test_uninstall_from_source(self):
        self.installer.install(self._plugin_struct(source='mock-plugin.tar'))
        self._assert_task_runnable('mock_plugin.tasks.run',
                                   expected_return='run')
        self.installer.uninstall(plugin=self._plugin_struct())
        self._assert_task_not_runnable('mock_plugin.tasks.run')

    def test_uninstall_from_source_with_deployment_id(self):
        deployment_id = 'deployment'
        self.installer.install(self._plugin_struct(source='mock-plugin.tar'),
                               deployment_id=deployment_id)
        self._assert_task_not_runnable('mock_plugin.tasks.run')
        self._assert_task_runnable('mock_plugin.tasks.run',
                                   expected_return='run',
                                   deployment_id=deployment_id)
        self.installer.uninstall(plugin=self._plugin_struct(),
                                 deployment_id=deployment_id)
        self._assert_task_not_runnable('mock_plugin.tasks.run',
                                       deployment_id=deployment_id)

    def test_install_from_wagon(self):
        with _patch_for_install_wagon(PACKAGE_NAME, PACKAGE_VERSION,
                                      download_path=self.wagons[PACKAGE_NAME]):
            self.installer.install(self._plugin_struct())
        self._assert_wagon_plugin_installed()

    # No forking on windows.
    @only_os('posix')
    def test_install_from_wagon_concurrent(self):
        fd, output_path = tempfile.mkstemp()
        os.close(fd)
        self.addCleanup(lambda: os.remove(output_path))
        with _patch_for_install_wagon(PACKAGE_NAME, PACKAGE_VERSION,
                                      download_path=self.wagons[PACKAGE_NAME]):
            class TestLoggingHandler(logging.Handler):
                def emit(self, record):
                    if 'Using' in record.message:
                        with open(output_path, 'w') as of:
                            of.write(record.message)
            handler = TestLoggingHandler()
            self.logger.addHandler(handler)
            try:
                def installer_func():
                    self.installer.install(self._plugin_struct())
                installers = [multiprocessing.Process(target=installer_func)
                              for _ in range(2)]
                for installer_process in installers:
                    installer_process.start()
                for installer_process in installers:
                    installer_process.join(timeout=100)
            finally:
                self.logger.removeHandler(handler)
        self._assert_wagon_plugin_installed()
        with open(output_path) as f:
            self.assertIn('Using existing installation of managed plugin',
                          f.read())

    def _assert_wagon_plugin_installed(self):
        self._assert_task_runnable('mock_plugin.tasks.run',
                                   expected_return='run',
                                   package_name=PACKAGE_NAME,
                                   package_version=PACKAGE_VERSION)
        self._assert_task_runnable(
            'mock_plugin.tasks.call_entry_point',
            expected_return='mock-plugin-entry-point',
            package_name=PACKAGE_NAME,
            package_version=PACKAGE_VERSION)

    def test_install_from_wagon_already_exists(self):
        self.test_install_from_wagon()
        # the installation here should basically do nothing but the
        # assertion should still pass
        self.test_install_from_wagon()

    def test_install_from_wagon_already_exists_but_missing_plugin_id(self):
        self.test_install_from_wagon()
        plugin_dir = self.installer._full_dst_dir('{0}-{1}'
                                                  .format(PACKAGE_NAME,
                                                          PACKAGE_VERSION))
        plugin_id_path = os.path.join(plugin_dir, 'plugin.id')
        os.remove(plugin_id_path)
        # the installation here should identify a plugin.id missing
        # and re-install the plugin
        with self.assertRaises(exceptions.PluginInstallationError) as c:
            self.test_install_from_wagon()
        self.assertIn('corrupted state', str(c.exception))

    def test_install_from_wagon_overriding_same_version(self):
        self.test_install_from_wagon()
        with _patch_for_install_wagon(
                PACKAGE_NAME, PACKAGE_VERSION,
                download_path=self.wagons['mock-plugin-modified'],
                plugin_id='2'):
            with self.assertRaises(exceptions.PluginInstallationError) as c:
                self.installer.install(self._plugin_struct())
            self.assertIn('does not match the ID', str(c.exception))

    def test_install_from_wagon_central_deployment(self):
        with _patch_for_install_wagon(PACKAGE_NAME, PACKAGE_VERSION,
                                      download_path=self.wagons[PACKAGE_NAME]):
            with self.assertRaises(exceptions.PluginInstallationError) as c:
                self.installer.install(self._plugin_struct(
                    executor='central_deployment_agent'),
                    deployment_id='deployment')
            self.assertIn('REST plugins API', str(c.exception))

    def test_uninstall_from_wagon(self):
        self.test_install_from_wagon()
        self.installer.uninstall_wagon(PACKAGE_NAME, PACKAGE_VERSION)
        self._assert_task_not_runnable('mock_plugin.tasks.run',
                                       package_name=PACKAGE_NAME,
                                       package_version=PACKAGE_VERSION)

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

    def test_install_no_source_or_managed_plugin(self):
        try:
            self.installer.install(self._plugin_struct())
            self.fail()
        except cloudify_exceptions.NonRecoverableError as e:
            self.assertIn('source or managed', str(e))

    def test_extract_package_name(self):
        package_dir = os.path.join(resources.get_resource('plugins'),
                                   'mock-plugin')
        self.assertEqual(
            'mock-plugin',
            installer.extract_package_name(package_dir))

    def test_install_dependencies_versions_conflict(self):
        def extract_requests_version():
            pip_freeze = self.installer._pip_freeze().split('\n')
            for package in pip_freeze:
                if package.startswith('requests=='):
                    requests_version = package.split('==')[0]
                    return requests_version
            raise AssertionError('Expected requests to be installed.')
        requests_plugin = test_utils.create_mock_plugin(
                basedir=self.plugins_work_dir,
                install_requires=['requests==2.6.0'])
        requests_tar = test_utils.create_plugin_tar(
                basedir=self.plugins_work_dir,
                plugin_dir_name=requests_plugin,
                target_directory=self.file_server_resource_base)
        requests_wagon = test_utils.create_plugin_wagon(
                basedir=self.plugins_work_dir,
                plugin_dir_name=requests_plugin,
                target_directory=self.file_server_resource_base)
        before_requests_version = extract_requests_version()
        plugin_struct = self._plugin_struct(source=requests_tar,
                                            name=requests_plugin)
        try:
            self.installer.install(plugin_struct)
            after_requests_version = extract_requests_version()
        finally:
            self.installer.uninstall(plugin=plugin_struct)
        self.assertEqual(before_requests_version, after_requests_version)
        try:
            with _patch_for_install_wagon(requests_plugin, '0.1',
                                          download_path=requests_wagon):
                self.installer.install(self._plugin_struct())
            after_requests_version = extract_requests_version()
        finally:
            self.installer.uninstall_wagon(requests_plugin, '0.1')
        self.assertEqual(before_requests_version, after_requests_version)


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


class TestGetManagedPlugin(BaseTest):

    def test_no_package_name(self):
        with _patch_client(plugins=[]) as client:
            self.assertIsNone(installer.get_managed_plugin(plugin={}))
            self.assertIsNone(client.plugins.kwargs)

    def test_no_managed_plugins(self):
        plugin = {'package_name': 'p', 'package_version': '1'}
        with _patch_client(plugins=[]) as client:
            self.assertIsNone(installer.get_managed_plugin(plugin=plugin))
            self.assertEqual(plugin, client.plugins.kwargs)

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
                  'distribution_release': 'x',
                  'package_version': '1'}
        with _patch_client(plugins=plugins):
            self.assertEquals('3',
                              installer.get_managed_plugin(plugin=plugin).id)

    @only_os('posix')
    def test_implicit_dist_and_dist_release(self):
        dist, _, dist_release = platform.linux_distribution(
            full_distribution_name=False)
        dist, dist_release = dist.lower(), dist_release.lower()
        plugins = [
            {'id': '1'},
            {'id': '2'},
            {'id': '3'},
            {'id': '4',
             'distribution': dist, 'distribution_release': dist_release},
            {'id': '5'},
        ]
        plugin = {'package_name': 'plugin', 'supported_platform': 'x',
                  'package_version': '1'}
        with _patch_client(plugins=plugins):
            self.assertEquals('4',
                              installer.get_managed_plugin(plugin=plugin).id)

    def test_list_filter_query_builder(self):
        plugin1 = {'package_name': 'a', 'package_version': '1'}
        plugin2 = {'package_name': 'a',
                   'package_version': '1',
                   'distribution': 'c',
                   'distribution_version': 'd',
                   'distribution_release': 'e',
                   'supported_platform': 'f'}
        for plugin in [plugin1, plugin2]:
            with _patch_client(plugins=[]) as client:
                installer.get_managed_plugin(plugin)
                self.assertEqual(plugin, client.plugins.kwargs)


@contextmanager
def _patch_for_install_wagon(package_name, package_version,
                             download_path, plugin_id='1'):
    plugin = {'package_name': package_name,
              'package_version': package_version,
              'supported_platform': 'any',
              'id': plugin_id}
    with _patch_client([plugin], download_path=download_path) as client:
        with patch('cloudify_agent.api.plugins.installer.get_managed_plugin',
                   lambda p, logger: client.plugins.plugins[0]):
            yield


@contextmanager
def _patch_client(plugins, download_path=None):
    plugins = [Plugin(p) for p in plugins]
    client = MockClient(plugins, download_path=download_path)
    with patch('cloudify_agent.api.plugins.installer.get_rest_client',
               lambda: client):
        yield client


class MockPlugins(object):
    def __init__(self, plugins, download_path=None):
        self.plugins = plugins
        self.download_path = download_path
        self.kwargs = None

    def list(self, **kwargs):
        self.kwargs = kwargs
        return self.plugins

    def download(self, output_file, **kwargs):
        shutil.copy(self.download_path, output_file)


class MockClient(object):
    def __init__(self, plugins, download_path=None):
        self.plugins = MockPlugins(plugins, download_path=download_path)
