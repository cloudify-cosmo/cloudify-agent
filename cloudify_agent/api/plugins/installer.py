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

import errno
import os
import sys
import shutil
import tempfile
import platform
import logging

import fasteners
from wagon import wagon
from wagon import utils as wagon_utils

from cloudify import ctx
from cloudify.exceptions import NonRecoverableError
from cloudify.exceptions import CommandExecutionException
from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner
from cloudify.manager import get_rest_client

from cloudify_agent import VIRTUALENV
from cloudify_agent.api import plugins
from cloudify_agent.api.utils import get_pip_path
from cloudify_agent.api import exceptions


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
        managed_plugin = get_managed_plugin(plugin,
                                            logger=self.logger)
        source = get_plugin_source(plugin, blueprint_id)
        args = get_plugin_args(plugin)
        tmp_plugin_dir = tempfile.mkdtemp(prefix='{0}-'.format(plugin['name']))
        constraint = os.path.join(tmp_plugin_dir, 'constraint.txt')
        with open(constraint, 'w') as f:
            f.write(self._pip_freeze())
        args = '{0} --prefix="{1}" --constraint="{2}"'.format(
                args, tmp_plugin_dir, constraint).strip()
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
        dst_dir = self._full_dst_dir(dst_dir)
        lock = self._lock(dst_dir)
        lock.acquire()
        try:
            if os.path.exists(dst_dir):
                plugin_id_path = os.path.join(dst_dir, 'plugin.id')
                if os.path.exists(plugin_id_path):
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
            w = wagon.Wagon(source=wagon_path)
            w.install(ignore_platform=True,
                      install_args=args,
                      virtualenv=VIRTUALENV)
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
        self.logger.info('Installing plugin from source')
        self._pip_install(source=source, args=args, constraint=constraint)
        shutil.move(tmp_plugin_dir, dst_dir)

    def _pip_freeze(self):
        try:
            return self.runner.run('{0} freeze'.format(get_pip_path())).std_out
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
            command = '{0} install {1} {2}'.format(
                get_pip_path(), plugin_dir, args)
            self.runner.run(command, cwd=plugin_dir)
            self.logger.debug('Retrieved package name: {0}'
                              .format(package_name))
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

    def uninstall(self, plugin, deployment_id=None):
        """Uninstall a previously installed plugin (only supports source
        plugins) """
        deployment_id = deployment_id or SYSTEM_DEPLOYMENT
        self.logger.info('Uninstalling plugin from source')
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
    def _full_dst_dir(dst_dir):
        plugins_dir = os.path.join(VIRTUALENV, 'plugins')
        return os.path.join(plugins_dir, ctx.tenant_name, dst_dir)

    @staticmethod
    def _lock(path):
        return fasteners.InterProcessLock('{0}.lock'.format(path))

    @staticmethod
    def _rmtree(path):
        shutil.rmtree(path, ignore_errors=True)


def extract_package_to_dir(package_url):
    """
    Extracts a pip package to a temporary directory.

    :param package_url: the URL to the package source.

    :return: the directory the package was extracted to.
    """

    # 1) Plugin installation during deployment creation occurs not in the main
    # thread, but rather in the local task thread pool.
    # When installing source based plugins, pip will install an
    # interrupt handler using signal.signal, this will fail saying something
    # like "signals are only allowed in the main thread"
    # from examining the code, I found patching signal in pip.util.ui
    # is the cleanest form. No "official" way of disabling this was found.
    # 2) pip.utils logger may be used internally by pip during some
    # ImportError. This interferes with our ZMQLoggingHandler which during
    # the first time it is invoked tries importing some stuff. This causes
    # a deadlock between the handler lock and the global import lock. One side
    # holds the import lock and tried writing to the logger and is blocked on
    # the handler lock, while the other side holds the handler lock and is
    # blocked on the import lock. This is why we patch the logging level
    # of this logger - by name, before importing pip. (see CFY-4866)
    _previous_signal = []
    _previous_level = []

    def _patch_pip_download():
        pip_utils_logger = logging.getLogger('pip.utils')
        _previous_level.append(pip_utils_logger.level)
        pip_utils_logger.setLevel(logging.CRITICAL)

        try:
            import pip.utils.ui

            def _stub_signal(sig, action):
                return None
            if hasattr(pip.utils.ui, 'signal'):
                _previous_signal.append(pip.utils.ui.signal)
                pip.utils.ui.signal = _stub_signal
        except ImportError:
            pass

    def _restore_pip_download():
        try:
            import pip.utils.ui
            if hasattr(pip.utils.ui, 'signal') and _previous_signal:
                pip.utils.ui.signal = _previous_signal[0]
        except ImportError:
            pass
        pip_utils_logger = logging.getLogger('pip.utils')
        pip_utils_logger.setLevel(_previous_level[0])

    plugin_dir = None
    try:
        plugin_dir = tempfile.mkdtemp()
        _patch_pip_download()
        # Import here, after patch
        import pip
        pip.download.unpack_url(link=pip.index.Link(package_url),
                                location=plugin_dir,
                                download_dir=None,
                                only_download=False)
    except Exception as e:
        if plugin_dir and os.path.exists(plugin_dir):
            shutil.rmtree(plugin_dir)
        raise exceptions.PluginInstallationError(
            'Failed to download and unpack package from {0}: {1}.'
            'You may consider uploading the plugin\'s Wagon archive '
            'to the manager, For more information please refer to '
            'the documentation.'.format(package_url, str(e)))
    finally:
        _restore_pip_download()

    return plugin_dir


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


def get_managed_plugin(plugin, logger=None):
    package_name = plugin.get('package_name')
    package_version = plugin.get('package_version')
    distribution = plugin.get('distribution')
    distribution_version = plugin.get('distribution_version')
    distribution_release = plugin.get('distribution_release')
    supported_platform = plugin.get('supported_platform')

    if not (package_name and package_version):
        if package_name and logger:
            logger.warn('package_name {0} is specified but no package_version '
                        'found, skipping wagon installation.'
                        .format(package_name))
        return None

    query_parameters = {
        'package_name': package_name,
        'package_version': package_version
    }
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

    # we return the first one because both package name and version
    # are required fields. No one pick is better than the other
    return plugins[0]


def _extract_platform_and_distro_info():
    current_platform = wagon_utils.get_platform()
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
        source = 'file://{0}'.format(plugin_zip)

    return source


def get_plugin_args(plugin):
    args = plugin.get('install_arguments') or ''
    return args.strip()
