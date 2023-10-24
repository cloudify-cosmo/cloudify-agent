import tempfile
import logging
import os
import pytest
import shutil
import threading
import subprocess
from contextlib import contextmanager

import wagon

from unittest.mock import patch

from cloudify import exceptions as cloudify_exceptions
from cloudify.state import ctx, current_ctx
from cloudify.utils import setup_logger, target_plugin_prefix, get_python_path
from cloudify.exceptions import NonRecoverableError
from cloudify_rest_client.plugins import Plugin
from cloudify_rest_client.constants import VisibilityState

try:
    from distro import linux_distribution
except ImportError:
    try:
        from platform import linux_distribution
    except ImportError:
        linux_distribution = None

from cloudify_agent.api import exceptions
from cloudify_agent.api.plugins import installer

from cloudify_agent.tests import resources
from cloudify_agent.tests import utils as test_utils
from cloudify_agent.tests import plugins


logger = setup_logger('api.plugins.test_installer',
                      logger_level=logging.DEBUG)


@pytest.mark.only_rabbit
def test_install_from_source(test_plugins, file_server):
    with _patch_client([]):
        installer.install(plugins.plugin_struct(file_server,
                                                source='mock-plugin.tar'))
    _assert_task_runnable('mock_plugin.tasks.run',
                          expected_return='run')
    _assert_task_runnable('mock_plugin.tasks.call_entry_point',
                          expected_return='mock-plugin-entry-point')


@pytest.mark.only_rabbit
def test_install_from_source_with_deployment_id(test_plugins, file_server):
    deployment_id = 'deployment'
    with _patch_client([]):
        installer.install(plugins.plugin_struct(file_server,
                          source='mock-plugin.tar'),
                          deployment_id=deployment_id)
        _assert_task_not_runnable('mock_plugin.tasks.run')
    _assert_task_runnable('mock_plugin.tasks.run',
                          expected_return='run',
                          deployment_id=deployment_id)


@pytest.mark.only_rabbit
def test_install_from_source_with_requirements(test_plugins, file_server):
    with _patch_client([]):
        installer.install(plugins.plugin_struct(
            file_server,
            source='mock-plugin-with-requirements.tar',
            args='-r requirements.txt'))
    _assert_task_runnable(
        'mock_with_install_args_for_test.module.do_stuff',
        expected_return='on the brilliant marble-sanded beaches of '
                        'Santraginus V')


@pytest.mark.only_rabbit
def test_uninstall_from_source(test_plugins, file_server):
    with _patch_client([]):
        installer.install(plugins.plugin_struct(file_server,
                                                source='mock-plugin.tar'))
    _assert_task_runnable('mock_plugin.tasks.run', expected_return='run')
    with _patch_client([]):
        installer.uninstall(plugin=plugins.plugin_struct(file_server))
        _assert_task_not_runnable('mock_plugin.tasks.run')


@pytest.mark.only_rabbit
def test_uninstall_from_source_with_deployment_id(test_plugins, file_server):
    deployment_id = 'deployment'
    with _patch_client([]):
        installer.install(
            plugins.plugin_struct(file_server, source='mock-plugin.tar'),
            deployment_id=deployment_id)
        _assert_task_not_runnable('mock_plugin.tasks.run')
    _assert_task_runnable('mock_plugin.tasks.run',
                          expected_return='run',
                          deployment_id=deployment_id)
    with _patch_client([]):
        installer.uninstall(plugin=plugins.plugin_struct(file_server),
                            deployment_id=deployment_id)
        _assert_task_not_runnable('mock_plugin.tasks.run',
                                  deployment_id=deployment_id)


@pytest.mark.only_rabbit
def test_install_from_wagon(test_plugins, file_server):
    with _patch_for_install_wagon(
        plugins.PACKAGE_NAME,
        plugins.PACKAGE_VERSION,
        download_path=test_plugins[plugins.PACKAGE_NAME],
    ):
        installer.install(plugins.plugin_struct(file_server))
    _assert_wagon_plugin_installed()


@pytest.mark.only_rabbit
def test_install_from_wagon_concurrent(test_plugins, file_server):
    ctx_obj = ctx._get_current_object()

    def installer_func(dep_id='__system__'):
        with current_ctx.push(ctx_obj):
            installer.install(plugins.plugin_struct(file_server), dep_id)

    installers = [threading.Thread(target=installer_func),
                  threading.Thread(target=installer_func, args=('id',))]

    with _patch_for_install_wagon(
        plugins.PACKAGE_NAME, plugins.PACKAGE_VERSION,
        download_path=test_plugins[plugins.PACKAGE_NAME],
        concurrent=True
    ), patch.object(ctx_obj, '_mock_context_logger') as mock_logger:
        for installer_process in installers:
            installer_process.start()
        for installer_process in installers:
            installer_process.join(timeout=100)

    _assert_wagon_plugin_installed()
    logs = [args[0] for level, args, kwargs in mock_logger.mock_calls]
    assert any('Using existing installation' in msg for msg in logs)


@pytest.mark.only_rabbit
def test_install_from_wagon_already_exists(test_plugins, file_server):
    test_install_from_wagon(test_plugins, file_server)
    # the installation here should basically do nothing but the
    # assertion should still pass
    test_install_from_wagon(test_plugins, file_server)


@pytest.mark.only_rabbit
def test_install_from_wagon_already_exists_missing_plugin_id(file_server,
                                                             test_plugins):
    test_install_from_wagon(test_plugins, file_server)
    plugin_dir = target_plugin_prefix(
        name=plugins.PACKAGE_NAME,
        version=plugins.PACKAGE_VERSION,
        tenant_name='default_tenant')
    plugin_id_path = os.path.join(plugin_dir, 'plugin.id')
    os.remove(plugin_id_path)
    # the installation here should identify a plugin.id missing
    # and re-install the plugin
    with pytest.raises(exceptions.PluginInstallationError,
                       match='.*corrupted state.*'):
        test_install_from_wagon(test_plugins, file_server)


@pytest.mark.only_rabbit
def test_install_from_wagon_overriding_same_version(test_plugins, file_server):
    test_install_from_wagon(test_plugins, file_server)
    with _patch_for_install_wagon(
            plugins.PACKAGE_NAME, plugins.PACKAGE_VERSION,
            download_path=test_plugins['mock-plugin-modified'],
            plugin_id='2'):
        with pytest.raises(exceptions.PluginInstallationError,
                           match='.*does not match the ID.*'):
            installer.install(plugins.plugin_struct(file_server))


def test_extract_package_to_dir(test_plugins, file_server):
    # create a plugin tar file and put it in the file server
    plugin_dir_name = 'mock-plugin-with-requirements'
    plugin_tar_name = test_utils.create_plugin_tar(
        plugin_dir_name,
        file_server.root_path)

    plugin_source_path = resources.get_resource(os.path.join(
        'plugins', plugin_dir_name))
    plugin_tar_url = '{0}/{1}'.format(file_server.url,
                                      plugin_tar_name)

    extracted_plugin_path = installer.extract_package_to_dir(
        plugin_tar_url)
    assert test_utils.are_dir_trees_equal(
        plugin_source_path,
        extracted_plugin_path)


def test_install_no_source_or_managed_plugin(file_server):
    with _patch_client([]):
        with pytest.raises(cloudify_exceptions.NonRecoverableError,
                           match='.*source or managed.*'):
            installer.install(plugins.plugin_struct(file_server))


def test_get_url_and_args_http_no_args():
    plugin = {'source': 'http://google.com'}
    url = installer.get_plugin_source(plugin)
    args = installer.get_plugin_args(plugin)
    assert url == 'http://google.com'
    assert args == []


def test_get_url_https():
    plugin = {
        'source': 'https://google.com',
        'install_arguments': '--pre'
    }
    url = installer.get_plugin_source(plugin)
    args = installer.get_plugin_args(plugin)

    assert url == 'https://google.com'
    assert args == ['--pre']


def test_get_url_faulty_schema():
    pytest.raises(NonRecoverableError,
                  installer.get_plugin_source,
                  {'source': 'bla://google.com'})


def test_get_plugin_source_from_blueprints_dir():
    plugin = {
        'source': 'plugin-dir-name'
    }
    file_path = '/tmp/plugin-dir-name.zip'
    with patch('cloudify.plugin_installer.ctx',
               **{'download_resource.return_value': file_path}):
        source = installer.get_plugin_source(
            plugin,
            blueprint_id='blueprint_id')
    prefix = 'file:///C:' if os.name == 'nt' else 'file://'
    expected = '{0}{1}'.format(prefix, file_path)
    assert expected == source


def test_no_package_name():
    with _patch_client(plugins=[]) as client:
        assert installer.get_managed_plugin(plugin={}) is None
        assert client.plugins.kwargs is None


def test_no_managed_plugins():
    plugin = {'package_name': 'p', 'package_version': '1'}
    with _patch_client(plugins=[]) as client:
        assert installer.get_managed_plugin(plugin=plugin) is None
        assert plugin == client.plugins.kwargs


def test_implicit_supported_platform():
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
def test_implicit_dist_and_dist_release():
    dist, _, dist_release = linux_distribution(full_distribution_name=False)
    dist, dist_release = dist.lower(), dist_release.lower()
    plugins = [
        {'id': '1', 'package_version': '1'},
        {'id': '2', 'package_version': '1'},
        {'id': '3', 'package_version': '1'},
        {'id': '4', 'package_version': '1',
         'supported_platform': 'any',
         'distribution': dist, 'distribution_release': dist_release},
        {'id': '5', 'package_version': '1'},
    ]
    plugin = {'package_name': 'plugin', 'supported_platform': 'x',
              'package_version': '1'}
    with _patch_client(plugins=plugins):
        assert '4' == installer.get_managed_plugin(plugin=plugin).id


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
        with patch('cloudify.plugin_installer.get_managed_plugin',
                   lambda p: client.plugins.plugins[0]):
            with patch('cloudify.plugin_installer.get_daemon_name',
                       return_value='agent'):
                yield


@contextmanager
def _patch_client(plugins, download_path=None, concurrent=False):
    plugins = [Plugin(p) for p in plugins]
    client = (MockConcurrentClient(plugins, download_path=download_path) if
              concurrent else MockClient(plugins, download_path=download_path))
    with patch('cloudify.plugin_installer.get_rest_client',
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

    def set_state(self, plugin_id, **kwargs):
        pass


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


class MockConcurrentClient(object):
    def __init__(self, plugins, download_path=None):
        self.plugins = ConcurrentMockPlugins(plugins,
                                             download_path=download_path)


def _run_task(task_name, expected_return=None,
              package_name=plugins.PACKAGE_NAME, package_version=None,
              deployment_id=None):
    prefix = target_plugin_prefix(
        package_name, tenant_name='default_tenant', version=package_version,
        deployment_id=deployment_id)
    python = get_python_path(prefix)
    package, func = task_name.rsplit('.', 1)
    env = os.environ.copy()
    env['PATH'] = '{0}{1}{2}'.format(
        os.path.dirname(python), os.pathsep, env['PATH'])

    return subprocess.check_output([
        python, '-c',
        'from {0} import {1}; print({1}())'.format(package, func)
    ], env=env).strip().decode('utf-8')


def _assert_task_runnable(task_name, expected_return=None, *args, **kwargs):
    assert _run_task(task_name, *args, **kwargs) == expected_return


def _assert_task_not_runnable(*args, **kwargs):
    # Exception, because it can be py2-OSError, IOError,
    # or py3-FileNotFoundError, depending what's wrong (not installed at all,
    # or malformed)
    pytest.raises(Exception, _run_task, *args, **kwargs)


def _assert_wagon_plugin_installed():
    _assert_task_runnable('mock_plugin.tasks.run',
                          expected_return='run',
                          package_name=plugins.PACKAGE_NAME,
                          package_version=plugins.PACKAGE_VERSION)
    _assert_task_runnable(
        'mock_plugin.tasks.call_entry_point',
        expected_return='mock-plugin-entry-point',
        package_name=plugins.PACKAGE_NAME,
        package_version=plugins.PACKAGE_VERSION)
