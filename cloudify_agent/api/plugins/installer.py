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

import os
import sys
import errno
import shutil
import tempfile
import platform

from urlparse import urljoin
from urllib import pathname2url

from os import walk
from distutils.version import LooseVersion

import wagon
import fasteners

from cloudify import ctx
from cloudify.utils import setup_logger
from cloudify.utils import extract_archive
from cloudify.manager import get_rest_client
from cloudify.utils import LocalCommandRunner
from cloudify.exceptions import NonRecoverableError
from cloudify.exceptions import CommandExecutionException

from cloudify_agent import VIRTUALENV
from cloudify_agent.api import plugins
from cloudify_agent.api import exceptions
from cloudify_agent.api.utils import get_pip_path
from cloudify_rest_client.constants import VisibilityState


SYSTEM_DEPLOYMENT = '__system__'


class PluginInstaller(object):

    def __init__(self, logger=None):
        self.logger = logger or setup_logger(self.__class__.__name__)
        self.runner = LocalCommandRunner(logger=self.logger)

    def install(self,
                plugin,
                deployment_id=None,
                blueprint_id=None):
        """
        Install the plugin to the current virtualenv.

        :param plugin: A plugin structure as defined in the blueprint.
        :param deployment_id: The deployment id associated with this
                              installation.
        :param blueprint_id: The blueprint id associated with this
                             installation. if specified, will be used
                             when downloading plugins that were included
                             as part of the blueprint itself.
        """
        # deployment_id may be empty in some tests.
        deployment_id = deployment_id or SYSTEM_DEPLOYMENT
        managed_plugin = get_managed_plugin(plugin)
        source = get_plugin_source(plugin, blueprint_id)
        args = get_plugin_args(plugin)
        tmp_plugin_dir = tempfile.mkdtemp(prefix='{0}-'.format(plugin['name']))
        constraint = os.path.join(tmp_plugin_dir, 'constraint.txt')
        with open(constraint, 'w') as f:
            f.write(self._pip_freeze())
        args.extend(['--prefix={0}'.format(tmp_plugin_dir),
                     '--constraint={0}'.format(constraint)])
        self._create_plugins_dir_if_missing()

        (current_platform,
         current_distro,
         current_distro_release) = _extract_platform_and_distro_info()

        self.logger.debug('Installing plugin {0} '
                          '[current_platform={1},'
                          ' current_distro={2},'
                          ' current_distro_release={3}]'
                          .format(plugin['name'],
                                  current_platform,
                                  current_distro,
                                  current_distro_release))

        try:
            if managed_plugin:
                self._install_managed_plugin(
                    deployment_id=deployment_id,
                    managed_plugin=managed_plugin,
                    plugin=plugin,
                    args=args,
                    tmp_plugin_dir=tmp_plugin_dir)
            elif source:
                self._install_source_plugin(
                    deployment_id=deployment_id,
                    plugin=plugin,
                    source=source,
                    args=args,
                    tmp_plugin_dir=tmp_plugin_dir,
                    constraint=constraint)
            else:
                raise NonRecoverableError(
                    'No source or managed plugin found for {0} '
                    '[current_platform={1},'
                    ' current_distro={2},'
                    ' current_distro_release={3}]'
                    .format(plugin,
                            current_platform,
                            current_distro,
                            current_distro_release))
        finally:
            self._rmtree(tmp_plugin_dir)

    def _install_managed_plugin(self,
                                deployment_id,
                                managed_plugin,
                                plugin,
                                args,
                                tmp_plugin_dir):
        matching_existing_installation = False
        dst_dir = '{0}-{1}'.format(managed_plugin.package_name,
                                   managed_plugin.package_version)
        dst_dir = self._full_dst_dir(dst_dir, managed_plugin)
        self.logger.debug('Checking if managed plugin installation exists '
                          'in {0}'.format(dst_dir))
        lock = self._lock(dst_dir)
        lock.acquire()
        try:
            if os.path.exists(dst_dir):
                self.logger.debug('Plugin path exists {0}'.format(dst_dir))
                plugin_id_path = os.path.join(dst_dir, 'plugin.id')
                if os.path.exists(plugin_id_path):
                    self.logger.debug('Plugin id path exists {0}'.
                                      format(plugin_id_path))
                    with open(plugin_id_path) as f:
                        existing_plugin_id = f.read().strip()
                    matching_existing_installation = (
                        existing_plugin_id == managed_plugin.id)
                    if not matching_existing_installation:
                        raise exceptions.PluginInstallationError(
                            'Managed plugin installation found but its ID '
                            'does not match the ID of the plugin currently '
                            'on the manager. [existing: {0}, new: {1}]'
                            .format(existing_plugin_id,
                                    managed_plugin.id))
                else:
                    raise exceptions.PluginInstallationError(
                        'Managed plugin installation found but it is '
                        'in a corrupted state. [{0}]'.format(managed_plugin))

            fields = ['package_name',
                      'package_version',
                      'supported_platform',
                      'distribution',
                      'distribution_release']
            description = ', '.join('{0}: {1}'.format(
                field, managed_plugin.get(field))
                for field in fields if managed_plugin.get(field))

            if matching_existing_installation:
                self.logger.info(
                    'Using existing installation of managed plugin: {0} [{1}]'
                    .format(managed_plugin.id, description))
            elif (deployment_id != SYSTEM_DEPLOYMENT and
                  plugin['executor'] == 'central_deployment_agent'):
                raise exceptions.PluginInstallationError(
                    'Central deployment agent managed plugins can only be '
                    'installed using the REST plugins API. [{0}]'
                    .format(managed_plugin))
            else:
                self.logger.info('Installing managed plugin: {0} [{1}]'
                                 .format(managed_plugin.id, description))
                try:
                    self._wagon_install(plugin=managed_plugin, args=args)
                    shutil.move(tmp_plugin_dir, dst_dir)
                    with open(os.path.join(dst_dir, 'plugin.id'), 'w') as f:
                        f.write(managed_plugin.id)
                except Exception as e:
                    tpe, value, tb = sys.exc_info()
                    raise NonRecoverableError('Failed installing managed '
                                              'plugin: {0} [{1}][{2}]'
                                              .format(managed_plugin.id,
                                                      plugin, e)), None, tb
        finally:
            if lock:
                lock.release()

    def _wagon_install(self, plugin, args):
        client = get_rest_client()
        wagon_dir = tempfile.mkdtemp(prefix='{0}-'.format(plugin.id))
        wagon_path = os.path.join(wagon_dir, 'wagon.tar.gz')
        try:
            self.logger.debug('Downloading plugin {0} from manager into {1}'
                              .format(plugin.id, wagon_path))
            client.plugins.download(plugin_id=plugin.id,
                                    output_file=wagon_path)
            self.logger.debug('Installing plugin {0} using wagon'
                              .format(plugin.id))
            wagon.install(
                wagon_path,
                ignore_platform=True,
                install_args=args,
                venv=VIRTUALENV
            )
        finally:
            self.logger.debug('Removing directory: {0}'
                              .format(wagon_dir))
            self._rmtree(wagon_dir)

    def _install_source_plugin(self,
                               deployment_id,
                               plugin,
                               source,
                               args,
                               tmp_plugin_dir,
                               constraint):
        dst_dir = '{0}-{1}'.format(deployment_id, plugin['name'])
        dst_dir = self._full_dst_dir(dst_dir)
        if os.path.exists(dst_dir):
            raise exceptions.PluginInstallationError(
                'Source plugin {0} already exists for deployment {1}. '
                'This probably means a previous deployment with the '
                'same name was not cleaned properly.'
                .format(plugin['name'], deployment_id))
        self.logger.info('Installing plugin from source: %s', plugin['name'])
        self._pip_install(source=source, args=args, constraint=constraint)
        shutil.move(tmp_plugin_dir, dst_dir)

    def _pip_freeze(self):
        try:
            return self.runner.run([get_pip_path(), 'freeze', '--all']).std_out
        except CommandExecutionException as e:
            raise exceptions.PluginInstallationError(
                'Failed running pip freeze. ({0})'.format(e))

    def _pip_install(self, source, args, constraint):
        plugin_dir = None
        try:
            if os.path.isabs(source):
                plugin_dir = source
            else:
                self.logger.debug('Extracting archive: {0}'.format(source))
                plugin_dir = extract_package_to_dir(source)
            package_name = extract_package_name(plugin_dir)
            if self._package_installed_in_agent_env(constraint, package_name):
                self.logger.warn('Skipping source plugin {0} installation, '
                                 'as the plugin is already installed in the '
                                 'agent virtualenv.'.format(package_name))
                return
            self.logger.debug('Installing from directory: {0} '
                              '[args={1}, package_name={2}]'
                              .format(plugin_dir, args, package_name))
            command = [get_pip_path(), 'install'] + args + [plugin_dir]

            self.runner.run(command=command, cwd=plugin_dir)
            self.logger.debug('Retrieved package name: {0}'
                              .format(package_name))
        except CommandExecutionException as e:
            self.logger.debug('Failed running pip install. Output:\n{0}'
                              .format(e.output))
            raise exceptions.PluginInstallationError(
                'Failed running pip install. ({0})'.format(e.error))
        finally:
            if plugin_dir and not os.path.isabs(source):
                self.logger.debug('Removing directory: {0}'
                                  .format(plugin_dir))
                self._rmtree(plugin_dir)

    @staticmethod
    def _package_installed_in_agent_env(constraint, package_name):
        package_name = package_name.lower()
        with open(constraint) as f:
            constraints = f.read().split(os.linesep)
        return any(
            (c.lower().startswith('{0}=='.format(package_name)) or
             'egg={0}'.format(package_name.replace('-', '_')) in c.lower())
            for c in constraints)

    def uninstall_source(self, plugin, deployment_id=None):
        """Uninstall a previously installed plugin (only supports source
        plugins) """
        deployment_id = deployment_id or SYSTEM_DEPLOYMENT
        self.logger.info('Uninstalling plugin from source: %s', plugin['name'])
        dst_dir = '{0}-{1}'.format(deployment_id, plugin['name'])
        dst_dir = self._full_dst_dir(dst_dir)
        if os.path.isdir(dst_dir):
            self._rmtree(dst_dir)

    def uninstall_wagon(self, package_name, package_version):
        """Uninstall a wagon (used by tests and by the plugins REST API)"""
        dst_dir = '{0}-{1}'.format(package_name, package_version)
        dst_dir = self._full_dst_dir(dst_dir)
        if os.path.isdir(dst_dir):
            self._rmtree(dst_dir)

        lock_file = '{0}.lock'.format(dst_dir)
        if os.path.exists(lock_file):
            os.remove(lock_file)

    def uninstall(self, plugin, delete_managed_plugins=True):
        if plugin.get('wagon'):
            if delete_managed_plugins:
                self.uninstall_wagon(
                    plugin['package_name'],
                    plugin['package_version']
                )
            else:
                self.logger.info('Not uninstalling managed plugin: {0} {1}'
                                 .format(plugin['package_name'],
                                         plugin['package_version']))
        else:
            self.uninstall_source(plugin, ctx.deployment.id)

    @staticmethod
    def _create_plugins_dir_if_missing():
        plugins_dir = os.path.join(VIRTUALENV, 'plugins')
        if not os.path.exists(plugins_dir):
            try:
                os.makedirs(plugins_dir)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise

    @staticmethod
    def _full_dst_dir(dst_dir, managed_plugin=None):
        if managed_plugin and managed_plugin['visibility'] \
                == VisibilityState.GLOBAL:
            tenant_name = managed_plugin['tenant_name']
        else:
            tenant_name = ctx.tenant_name
        plugins_dir = os.path.join(VIRTUALENV, 'plugins')
        return os.path.join(plugins_dir, tenant_name, dst_dir)

    @staticmethod
    def _lock(path):
        return fasteners.InterProcessLock('{0}.lock'.format(path))

    @staticmethod
    def _rmtree(path):
        shutil.rmtree(path, ignore_errors=True)


def extract_package_to_dir(package_url):
    """
    Using a subprocess to extract a pip package to a temporary directory.
    :param: package_url: the URL of the package source.
    :return: the directory the package was extracted to.

    """
    plugin_dir = None
    archive_dir = tempfile.mkdtemp()
    runner = LocalCommandRunner()

    try:
        # We run `pip download` command in a subprocess to support
        # multi-threaded scenario (i.e snapshot restore).
        # We don't use `curl` because pip can handle different kinds of files,
        # including .git.
        command = [get_pip_path(), 'download', '-d',
                   archive_dir, '--no-deps', package_url]
        runner.run(command=command)
        archive = _get_archive(archive_dir, package_url)
        plugin_dir_parent = extract_archive(archive)
        plugin_dir = _get_plugin_path(plugin_dir_parent, package_url)

    except NonRecoverableError as e:
        if plugin_dir and os.path.exists(plugin_dir):
            shutil.rmtree(plugin_dir)
        raise e

    finally:
        if os.path.exists(archive_dir):
            shutil.rmtree(archive_dir)

    return plugin_dir


def _get_plugin_path(plugin_dir_parent, package_url):
    """
    plugin_dir_parent is a directory containing the plugin dir. Since we
    need the plugin`s dir, we find it's name and concatenate it to the
    plugin_dir_parent.
    """
    contents = list(walk(plugin_dir_parent))
    if len(contents) < 1:
        _remove_tempdir_and_raise_proper_exception(package_url,
                                                   plugin_dir_parent)
    parent_dir_content = contents[0]
    plugin_dir_name = parent_dir_content[1][0]
    return os.path.join(plugin_dir_parent, plugin_dir_name)


def _assert_list_len(l, expected_len, package_url, archive_dir):
    if len(l) != expected_len:
        _remove_tempdir_and_raise_proper_exception(package_url, archive_dir)


def _remove_tempdir_and_raise_proper_exception(package_url, tempdir):
    if tempdir and os.path.exists(tempdir):
        shutil.rmtree(tempdir)
    raise exceptions.PluginInstallationError(
        'Failed to download package from {0}.'
        'You may consider uploading the plugin\'s Wagon archive '
        'to the manager, For more information please refer to '
        'the documentation.'.format(package_url))


def _get_archive(archive_dir, package_url):
    """
    archive_dir contains a zip file with the plugin directory. This function
    finds the name of that zip file and returns the full path to it (the full
    path is required in order to extract it)
    """
    contents = list(walk(archive_dir))
    _assert_list_len(contents, 1, package_url, archive_dir)
    files = contents[0][2]
    _assert_list_len(files, 1, package_url, archive_dir)
    return os.path.join(archive_dir, files[0])


def extract_package_name(package_dir):
    """
    Detects the package name of the package located at 'package_dir' as
    specified in the package setup.py file.

    :param package_dir: the directory the package was extracted to.

    :return: the package name
    """
    runner = LocalCommandRunner()
    plugin_name = runner.run(
        '{0} {1} {2}'.format(
            sys.executable,
            os.path.join(os.path.dirname(plugins.__file__),
                         'extract_package_name.py'),
            package_dir),
        cwd=package_dir
    ).std_out
    return plugin_name


def get_managed_plugin(plugin):
    package_name = plugin.get('package_name')
    package_version = plugin.get('package_version')
    distribution = plugin.get('distribution')
    distribution_version = plugin.get('distribution_version')
    distribution_release = plugin.get('distribution_release')
    supported_platform = plugin.get('supported_platform')
    if not package_name:
        return None
    query_parameters = {'package_name': package_name}
    if package_version:
        query_parameters['package_version'] = package_version
    if distribution:
        query_parameters['distribution'] = distribution
    if distribution_version:
        query_parameters['distribution_version'] = distribution_version
    if distribution_release:
        query_parameters['distribution_release'] = distribution_release
    if supported_platform:
        query_parameters['supported_platform'] = supported_platform
    client = get_rest_client()
    plugins = client.plugins.list(**query_parameters)

    (current_platform,
     a_dist,
     a_dist_release) = _extract_platform_and_distro_info()

    if not supported_platform:
        plugins = [p for p in plugins
                   if p.supported_platform in ['any', current_platform]]
    if os.name != 'nt':
        if not distribution:
            plugins = [p for p in plugins
                       if p.supported_platform == 'any' or
                       p.distribution == a_dist]
        if not distribution_release:
            plugins = [p for p in plugins
                       if p.supported_platform == 'any' or
                       p.distribution_release == a_dist_release]

    if not plugins:
        return None

    # in case version was not specified, return the latest
    plugins.sort(key=lambda plugin: LooseVersion(plugin['package_version']),
                 reverse=True)
    return plugins[0]


def _extract_platform_and_distro_info():
    current_platform = wagon.get_platform()
    distribution, _, distribution_release = platform.linux_distribution(
        full_distribution_name=False)
    return current_platform, distribution.lower(), distribution_release.lower()


def get_plugin_source(plugin, blueprint_id=None):

    source = plugin.get('source') or ''
    if not source:
        return None
    source = source.strip()

    # validate source url
    if '://' in source:
        split = source.split('://')
        schema = split[0]
        if schema not in ['http', 'https']:
            # invalid schema
            raise NonRecoverableError('Invalid schema: {0}'.format(schema))
    else:
        # Else, assume its a relative path from <blueprint_home>/plugins
        # to a directory containing the plugin archive.
        # in this case, the archived plugin is expected to reside on the
        # manager file server as a zip file.
        if blueprint_id is None:
            raise ValueError('blueprint_id must be specified when plugin '
                             'source does not contain a schema')

        plugin_zip = ctx.download_resource('plugins/{0}.zip'.format(source))
        source = path_to_file_url(plugin_zip)

    return source


def get_plugin_args(plugin):
    args = plugin.get('install_arguments') or ''
    return args.strip().split()


def path_to_file_url(path):
    """
    Convert a path to a file: URL.  The path will be made absolute and have
    quoted path parts.
    As taken from: https://github.com/pypa/pip/blob/9.0.1/pip/download.py#L459
    """
    path = os.path.normpath(os.path.abspath(path))
    url = urljoin('file:', pathname2url(path))
    return url
