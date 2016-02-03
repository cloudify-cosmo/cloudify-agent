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

import fasteners
import pip
from wagon import wagon
from wagon import utils as wagon_utils

from cloudify.exceptions import NonRecoverableError
from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner
from cloudify.utils import get_manager_file_server_blueprints_root_url
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
        args = '{0} --prefix="{1}"'.format(args, tmp_plugin_dir).strip()
        self._create_plugins_dir_if_missing()
        try:
            if managed_plugin:
                self._install_managed_plugin(
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
                    tmp_plugin_dir=tmp_plugin_dir)
            else:
                raise NonRecoverableError(
                    'No source or managed plugin found for {0}'.format(plugin))
        finally:
            self._rmtree(tmp_plugin_dir)

    def _install_managed_plugin(self, managed_plugin, plugin, args,
                                tmp_plugin_dir):
        matching_existing_installation = False
        package_name = managed_plugin.package_name
        dst_dir = '{0}-{1}'.format(package_name,
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
                        self.logger.warning(
                            'Managed plugin installation found but its ID '
                            'does not match the ID of the plugin currently'
                            ' on the manager. Existing '
                            'installation will be overridden. '
                            '[existing: {0}]'.format(existing_plugin_id))
                        self._rmtree(dst_dir)
                else:
                    self.logger.warning(
                        'Managed plugin installation found but it is '
                        'in a corrupted state. Existing installation '
                        'will be overridden.')
                    self._rmtree(dst_dir)

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
                    'Skipping installation of managed plugin: {0} '
                    'as it is already installed [{1}]'
                    .format(managed_plugin.id, description))
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

    def _install_source_plugin(self, deployment_id, plugin, source, args,
                               tmp_plugin_dir):
        dst_dir = '{0}-{1}'.format(deployment_id, plugin['name'])
        dst_dir = self._full_dst_dir(dst_dir)
        if os.path.exists(dst_dir):
            self.logger.warning(
                'Source plugin {0} already exists for deployment {1}. '
                'This probably means a previous deployment with the '
                'same name was not cleaned properly. Removing existing'
                ' directory'.format(plugin['name'], deployment_id))
            self._rmtree(dst_dir)
        self.logger.info('Installing plugin from source')
        self._pip_install(source=source, args=args)
        shutil.move(tmp_plugin_dir, dst_dir)

    def _pip_install(self, source, args):
        plugin_dir = None
        try:
            if os.path.isabs(source):
                plugin_dir = source
            else:
                self.logger.debug('Extracting archive: {0}'.format(source))
                plugin_dir = extract_package_to_dir(source)
            self.logger.debug('Installing from directory: {0} '
                              '[args={1}]'.format(plugin_dir, args))
            command = '{0} install {1} {2}'.format(
                get_pip_path(), plugin_dir, args)
            self.runner.run(command, cwd=plugin_dir)
            package_name = extract_package_name(plugin_dir)
            self.logger.debug('Retrieved package name: {0}'
                              .format(package_name))
        finally:
            if plugin_dir and not os.path.isabs(source):
                self.logger.debug('Removing directory: {0}'
                                  .format(plugin_dir))
                self._rmtree(plugin_dir)
        return package_name

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
        """Only used by tests for cleanup purposes"""
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
        return os.path.join(plugins_dir, dst_dir)

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

    # Plugin installation during deployment creation occurs not in the main
    # thread, but rather in the local task thread pool.
    # When installing source based plugins, pip will install an
    # interrupt handler using signal.signal, this will fail saying something
    # like "signals are only allowed in the main thread"
    # from examining the code, I found patching signal in pip.util.ui
    # is the cleanest form. No "official" way of disabling this was found.
    _previous_signal = []

    def _patch_pip_download():
        try:
            import pip.utils.ui
        except ImportError:
            return

        def _stub_signal(sig, action):
            return None
        if hasattr(pip.utils.ui, 'signal'):
            _previous_signal.append(pip.utils.ui.signal)
            pip.utils.ui.signal = _stub_signal

    def _restore_pip_download():
        try:
            import pip.utils.ui
        except ImportError:
            return
        if hasattr(pip.utils.ui, 'signal') and _previous_signal:
            pip.utils.ui.signal = _previous_signal[0]

    plugin_dir = None

    try:
        plugin_dir = tempfile.mkdtemp()
        _patch_pip_download()
        # check pip version and unpack plugin_url accordingly
        if is_pip6_or_higher():
            pip.download.unpack_url(link=pip.index.Link(package_url),
                                    location=plugin_dir,
                                    download_dir=None,
                                    only_download=False)
        else:
            req_set = pip.req.RequirementSet(build_dir=None,
                                             src_dir=None,
                                             download_dir=None)
            req_set.unpack_url(link=pip.index.Link(package_url),
                               location=plugin_dir,
                               download_dir=None,
                               only_download=False)
    except Exception as e:
        if plugin_dir and os.path.exists(plugin_dir):
            shutil.rmtree(plugin_dir)
        raise exceptions.PluginInstallationError(
            'Failed to download and unpack package from {0}: {1}'
            .format(package_url, str(e)))
    finally:
        _restore_pip_download()

    return plugin_dir


def is_pip6_or_higher(pip_version=None):

    """
    Determines if the pip version passed is higher than version 6.

    :param pip_version: the version of pip

    :return: whether or not the version is higher than version 6.
    """

    major, minor, micro = parse_pip_version(pip_version)
    if int(major) >= 6:
        return True
    else:
        return False


def parse_pip_version(pip_version=''):
    """
    Parses a pip version string to identify major, minor, micro versions.

    :param pip_version: the version of pip

    :return: major, minor, micro version of pip
    :rtype: tuple
    """

    if not pip_version:
        try:
            pip_version = pip.__version__
        except AttributeError as e:
            raise exceptions.PluginInstallationError(
                'Failed to get pip version: ', str(e))

    if not isinstance(pip_version, basestring):
        raise exceptions.PluginInstallationError(
            'Invalid pip version: {0} is not a string'
            .format(pip_version))

    if not pip_version.__contains__("."):
        raise exceptions.PluginInstallationError(
            'Unknown formatting of pip version: "{0}", expected '
            'dot-delimited numbers (e.g. "1.5.4", "6.0")'
            .format(pip_version))

    version_parts = pip_version.split('.')
    major = version_parts[0]
    minor = version_parts[1]
    micro = ''
    if len(version_parts) > 2:
        micro = version_parts[2]

    if not str(major).isdigit():
        raise exceptions.PluginInstallationError(
            'Invalid pip version: "{0}", major version is "{1}" '
            'while expected to be a number'
            .format(pip_version, major))

    if not str(minor).isdigit():
        raise exceptions.PluginInstallationError(
            'Invalid pip version: "{0}", minor version is "{1}" while '
            'expected to be a number'
            .format(pip_version, minor))

    return major, minor, micro


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

    if not supported_platform:
        current_platform = wagon_utils.get_platform()
        plugins = [p for p in plugins
                   if p.supported_platform in ['any', current_platform]]
    if os.name != 'nt':
        a_dist, _, a_dist_release = platform.linux_distribution(
            full_distribution_name=False)
        a_dist, a_dist_release = a_dist.lower(), a_dist_release.lower()
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
        blueprints_root = get_manager_file_server_blueprints_root_url()
        blueprint_plugins_url = '{0}/{1}/plugins'.format(
            blueprints_root, blueprint_id)

        source = '{0}/{1}.zip'.format(blueprint_plugins_url, source)

    return source


def get_plugin_args(plugin):
    args = plugin.get('install_arguments') or ''
    return args.strip()
