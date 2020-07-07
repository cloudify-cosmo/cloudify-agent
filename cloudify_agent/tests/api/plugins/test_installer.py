import tempfile
import logging
import os
import platform
import pytest
import shutil
import threading
from contextlib import contextmanager

import wagon

from mock import patch

from cloudify import dispatch
from cloudify import exceptions as cloudify_exceptions
from cloudify.state import ctx, current_ctx
from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner
from cloudify.exceptions import NonRecoverableError
from cloudify_rest_client.plugins import Plugin
from cloudify_rest_client.constants import VisibilityState

from cloudify_agent.api import exceptions
from cloudify_agent.api.plugins import installer

from cloudify_agent.tests import resources
from cloudify_agent.tests import utils as test_utils
from cloudify_agent.tests import BaseTest


PLUGIN_NAME = 'plugin'
PACKAGE_NAME = 'mock-plugin'
PACKAGE_VERSION = '1.0'


class PluginInstallerTest(BaseTest):

    @classmethod
    def setUpClass(cls):
        cls.logger = setup_logger(cls.__name__, logger_level=logging.DEBUG)
        cls.runner = LocalCommandRunner(cls.logger)

        cls.plugins_work_dir = tempfile.mkdtemp(
            prefix='plugins-work-dir-')
        cls.file_server_resource_base = tempfile.mkdtemp(
            prefix='file-server-resource-base-')
        cls.fs = test_utils.FileServer(
            root_path=cls.file_server_resource_base, ssl=False)
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
        super(PluginInstallerTest, self).setUp()
        self.mock_ctx_with_tenant()

    def tearDown(self):
        super(PluginInstallerTest, self).tearDown()
        installer.uninstall_source(plugin=self._plugin_struct(''))
        installer.uninstall_source(plugin=self._plugin_struct(''),
                                   deployment_id='deployment')
        installer.uninstall_wagon(PACKAGE_NAME, PACKAGE_VERSION)

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
        assert (
            dispatch.dispatch(test_utils.op_context(
                task_name,
                plugin_name=PLUGIN_NAME,
                package_name=package_name,
                package_version=package_version,
                deployment_id=deployment_id))
        ) == expected_return

    def _assert_task_not_runnable(self, task_name,
                                  deployment_id=None,
                                  package_name=None,
                                  package_version=None):
        pytest.raises(
            cloudify_exceptions.NonRecoverableError,
            dispatch.dispatch,
            test_utils.op_context(task_name,
                                  plugin_name=PLUGIN_NAME,
                                  deployment_id=deployment_id,
                                  package_name=package_name,
                                  package_version=package_version))

    def test_install_from_source(self):
        installer.install(self._plugin_struct(source='mock-plugin.tar'))
        self._assert_task_runnable('mock_plugin.tasks.run',
                                   expected_return='run')
        self._assert_task_runnable('mock_plugin.tasks.call_entry_point',
                                   expected_return='mock-plugin-entry-point')

    def test_install_from_source_with_deployment_id(self):
        deployment_id = 'deployment'
        installer.install(self._plugin_struct(source='mock-plugin.tar'),
                          deployment_id=deployment_id)
        self._assert_task_not_runnable('mock_plugin.tasks.run')
        self._assert_task_runnable('mock_plugin.tasks.run',
                                   expected_return='run',
                                   deployment_id=deployment_id)

    def test_install_from_source_with_requirements(self):
        installer.install(self._plugin_struct(
            source='mock-plugin-with-requirements.tar',
            args='-r requirements.txt'))
        self._assert_task_runnable(
            'mock_with_install_args_for_test.module.do_stuff',
            expected_return='on the brilliant marble-sanded beaches of '
                            'Santraginus V')

    def test_install_from_source_already_exists(self):
        installer.install(self._plugin_struct(source='mock-plugin.tar'))
        with pytest.raises(exceptions.PluginInstallationError,
                           match='.*already exists.*'):
            installer.install(self._plugin_struct(source='mock-plugin.tar'))

    def test_uninstall_from_source(self):
        installer.install(self._plugin_struct(source='mock-plugin.tar'))
        self._assert_task_runnable('mock_plugin.tasks.run',
                                   expected_return='run')
        installer.uninstall_source(plugin=self._plugin_struct())
        self._assert_task_not_runnable('mock_plugin.tasks.run')

    def test_uninstall_from_source_with_deployment_id(self):
        deployment_id = 'deployment'
        installer.install(self._plugin_struct(source='mock-plugin.tar'),
                          deployment_id=deployment_id)
        self._assert_task_not_runnable('mock_plugin.tasks.run')
        self._assert_task_runnable('mock_plugin.tasks.run',
                                   expected_return='run',
                                   deployment_id=deployment_id)
        installer.uninstall_source(plugin=self._plugin_struct(),
                                   deployment_id=deployment_id)
        self._assert_task_not_runnable('mock_plugin.tasks.run',
                                       deployment_id=deployment_id)

    def test_install_from_wagon(self):
        with _patch_for_install_wagon(PACKAGE_NAME, PACKAGE_VERSION,
                                      download_path=self.wagons[PACKAGE_NAME]):
            installer.install(self._plugin_struct())
        self._assert_wagon_plugin_installed()

    def test_install_from_wagon_concurrent(self):
        ctx_obj = ctx._get_current_object()

        def installer_func(dep_id='__system__'):
            with current_ctx.push(ctx_obj):
                installer.install(self._plugin_struct(), dep_id)

        installers = [threading.Thread(target=installer_func),
                      threading.Thread(target=installer_func, args=('id',))]

        with _patch_for_install_wagon(PACKAGE_NAME, PACKAGE_VERSION,
                                      download_path=self.wagons[PACKAGE_NAME],
                                      concurrent=True), \
                patch.object(ctx_obj, '_mock_context_logger') as mock_logger:
            for installer_process in installers:
                installer_process.start()
            for installer_process in installers:
                installer_process.join(timeout=100)

        self._assert_wagon_plugin_installed()
        logs = [args[0] for level, args, kwargs in mock_logger.mock_calls]
        assert any('Using existing installation' in msg for msg in logs)

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
        plugin_dir = installer._full_dst_dir(
            '{0}-{1}'.format(PACKAGE_NAME, PACKAGE_VERSION))
        plugin_id_path = os.path.join(plugin_dir, 'plugin.id')
        os.remove(plugin_id_path)
        # the installation here should identify a plugin.id missing
        # and re-install the plugin
        with pytest.raises(exceptions.PluginInstallationError,
                           match='.*corrupted state.*'):
            self.test_install_from_wagon()

    def test_install_from_wagon_overriding_same_version(self):
        self.test_install_from_wagon()
        with _patch_for_install_wagon(
                PACKAGE_NAME, PACKAGE_VERSION,
                download_path=self.wagons['mock-plugin-modified'],
                plugin_id='2'):
            with pytest.raises(exceptions.PluginInstallationError,
                               match='.*does not match the ID.*'):
                installer.install(self._plugin_struct())

    def test_install_from_wagon_central_deployment(self):
        with _patch_for_install_wagon(PACKAGE_NAME, PACKAGE_VERSION,
                                      download_path=self.wagons[PACKAGE_NAME],
                                      archive_name='some_archive'):
            with pytest.raises(exceptions.PluginInstallationError,
                               match='.*REST plugins API.*'):
                installer.install(self._plugin_struct(
                    executor='central_deployment_agent'),
                    deployment_id='deployment')

    def test_uninstall_from_wagon(self):
        self.test_install_from_wagon()
        installer.uninstall_wagon(PACKAGE_NAME, PACKAGE_VERSION)
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
        assert test_utils.are_dir_trees_equal(
            plugin_source_path,
            extracted_plugin_path)

    def test_install_no_source_or_managed_plugin(self):
        with pytest.raises(cloudify_exceptions.NonRecoverableError,
                           match='.*source or managed.*'):
            installer.install(self._plugin_struct())

    def test_extract_package_name(self):
        package_dir = os.path.join(resources.get_resource('plugins'),
                                   'mock-plugin')
        assert 'mock-plugin' == installer.extract_package_name(package_dir)


class TestGetSourceAndGetArgs(BaseTest):

    def test_get_url_and_args_http_no_args(self):
        plugin = {'source': 'http://google.com'}
        url = installer.get_plugin_source(plugin)
        args = installer.get_plugin_args(plugin)
        assert url == 'http://google.com'
        assert args == []

    def test_get_url_https(self):
        plugin = {
            'source': 'https://google.com',
            'install_arguments': '--pre'
        }
        url = installer.get_plugin_source(plugin)
        args = installer.get_plugin_args(plugin)

        assert url == 'https://google.com'
        assert args == ['--pre']

    def test_get_url_faulty_schema(self):
        pytest.raises(NonRecoverableError,
                      installer.get_plugin_source,
                      {'source': 'bla://google.com'})

    def test_get_plugin_source_from_blueprints_dir(self):
        plugin = {
            'source': 'plugin-dir-name'
        }
        file_path = '/tmp/plugin-dir-name.zip'
        with patch('cloudify_agent.api.plugins.installer.ctx',
                   **{'download_resource.return_value': file_path}):
            source = installer.get_plugin_source(
                plugin,
                blueprint_id='blueprint_id')
        prefix = 'file:///C:' if os.name == 'nt' else 'file://'
        expected = '{0}{1}'.format(prefix, file_path)
        assert expected == source


class TestGetManagedPlugin(BaseTest):

    def test_no_package_name(self):
        with _patch_client(plugins=[]) as client:
            assert installer.get_managed_plugin(plugin={}) is None
            assert client.plugins.kwargs is None

    def test_no_managed_plugins(self):
        plugin = {'package_name': 'p', 'package_version': '1'}
        with _patch_client(plugins=[]) as client:
            assert installer.get_managed_plugin(plugin=plugin) is None
            assert plugin == client.plugins.kwargs

    def test_implicit_supported_platform(self):
        plugins = [
            {'id': '1', 'package_version': '1'},
            {'id': '2', 'package_version': '1'},
            {'id': '3', 'package_version': '1',
             'supported_platform': wagon.get_platform()},
            {'id': '4', 'package_version': '1'},
            {'id': '5', 'package_version': '1'},
        ]
        plugin = {'package_name': 'plugin', 'distribution': 'x',
                  'distribution_release': 'x',
                  'package_version': '1'}
        with _patch_client(plugins=plugins):
            assert '3' == installer.get_managed_plugin(plugin=plugin).id

    @pytest.mark.only_posix
    def test_implicit_dist_and_dist_release(self):
        dist, _, dist_release = platform.linux_distribution(
            full_distribution_name=False)
        dist, dist_release = dist.lower(), dist_release.lower()
        plugins = [
            {'id': '1', 'package_version': '1'},
            {'id': '2', 'package_version': '1'},
            {'id': '3', 'package_version': '1'},
            {'id': '4', 'package_version': '1',
             'distribution': dist, 'distribution_release': dist_release},
            {'id': '5', 'package_version': '1'},
        ]
        plugin = {'package_name': 'plugin', 'supported_platform': 'x',
                  'package_version': '1'}
        with _patch_client(plugins=plugins):
            assert '4' == installer.get_managed_plugin(plugin=plugin).id

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
                assert plugin == client.plugins.kwargs


@contextmanager
def _patch_for_install_wagon(package_name, package_version,
                             download_path, plugin_id='1',
                             archive_name='installing-archive_name',
                             concurrent=False):
    plugin = {'package_name': package_name,
              'package_version': package_version,
              'supported_platform': 'any',
              'id': plugin_id,
              'visibility': VisibilityState.TENANT,
              'archive_name': archive_name}
    with _patch_client([plugin], download_path=download_path,
                       concurrent=concurrent) as client:
        with patch('cloudify_agent.api.plugins.installer.get_managed_plugin',
                   lambda p: client.plugins.plugins[0]):
            yield


@contextmanager
def _patch_client(plugins, download_path=None, concurrent=False):
    plugins = [Plugin(p) for p in plugins]
    client = (MockConcurrentClinet(plugins, download_path=download_path) if
              concurrent else MockClient(plugins, download_path=download_path))
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

    def get(self, plugin_id):
        for plugin in self.plugins:
            if plugin['id'] == plugin_id:
                return plugin

    def finish_installation(self, plugin_id):
        plugin = self.get(plugin_id)
        plugin['archive_name'] = 'archive_name'
        return plugin


class ConcurrentMockPlugins(MockPlugins):
    def __init__(self, plugins, **kwargs):
        fd, output_path = tempfile.mkstemp()
        os.close(fd)
        self.output_path = output_path
        super(ConcurrentMockPlugins, self).__init__(plugins, **kwargs)

    def get(self, plugin_id):
        plugin = super(ConcurrentMockPlugins, self).get(plugin_id)
        with open(self.output_path, 'r') as output:
            if ('finished installation for plugin id {0}'.format(plugin_id)
                    in output.read()):
                plugin['archive_name'] = 'archive_name'

        return plugin

    def finish_installation(self, plugin_id):
        with open(self.output_path, 'w') as output:
            output.write('finished installation for plugin id {0}'.
                         format(plugin_id))
            super(ConcurrentMockPlugins, self).finish_installation(plugin_id)


class MockClient(object):
    def __init__(self, plugins, download_path=None):
        self.plugins = MockPlugins(plugins, download_path=download_path)


class MockConcurrentClinet(object):
    def __init__(self, plugins, download_path=None):
        self.plugins = ConcurrentMockPlugins(plugins,
                                             download_path=download_path)
