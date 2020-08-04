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
import glob
import json
import time
import errno
import shutil
import tempfile
import platform
import threading

from os import walk
from contextlib import contextmanager

import wagon
import fasteners

from cloudify import ctx
from cloudify.manager import get_rest_client
from cloudify.constants import MANAGER_PLUGINS_PATH
from cloudify.utils import extract_archive, get_python_path
from cloudify.utils import LocalCommandRunner, target_plugin_prefix
from cloudify._compat import reraise, urljoin, pathname2url, parse_version
from cloudify.exceptions import NonRecoverableError, CommandExecutionException

from cloudify_agent import VIRTUALENV
from cloudify_agent.api import plugins
from cloudify_agent.api import exceptions

try:
    from cloudify_premium import syncthing_utils
except ImportError:
    syncthing_utils = None

SYSTEM_DEPLOYMENT = '__system__'
SYNCTHING_QUERY_INTERVAL = 1
PLUGIN_QUERY_INTERVAL = 1
INSTALLATION_TIMEOUT = 75
PLUGIN_INSTALL_LOCK = threading.Lock()


runner = LocalCommandRunner()


def install(plugin,
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
    managed_plugin = get_managed_plugin(plugin)
    source = get_plugin_source(plugin, blueprint_id)
    args = get_plugin_args(plugin)
    _create_plugins_dir_if_missing()
    if managed_plugin:
        _install_managed_plugin(
            managed_plugin=managed_plugin,
            args=args)
    elif source:
        _install_source_plugin(
            deployment_id=deployment_id,
            plugin=plugin,
            source=source,
            args=args)
    else:
        platform, distro, release = _extract_platform_and_distro_info()
        raise NonRecoverableError(
            'No source or managed plugin found for {0} '
            '[current platform={1}, distro={2}, release={3}]'
            .format(plugin, platform, distro, release))


def _make_virtualenv(path):
    """Make a venv and link the current venv to it.

    The new venv will have the current venv linked, ie. it will be
    able to import libraries from the current venv, but libraries
    installed directly will have precedence.
    """
    runner.run([
        sys.executable, '-m', 'virtualenv',
        '--no-download',
        '--no-pip', '--no-wheel', '--no-setuptools',
        path
    ])
    _link_virtualenv(path)


def is_already_installed(dst_dir, plugin_id):
    ctx.logger.debug('Checking if managed plugin installation exists '
                     'in %s', dst_dir)
    if os.path.exists(dst_dir):
        ctx.logger.debug('Plugin path exists: %s', dst_dir)
        plugin_id_path = os.path.join(dst_dir, 'plugin.id')
        if os.path.exists(plugin_id_path):
            ctx.logger.debug('Plugin id path exists: %s', plugin_id_path)
            with open(plugin_id_path) as f:
                existing_plugin_id = f.read().strip()
            if existing_plugin_id == plugin_id:
                return True
            else:
                raise exceptions.PluginInstallationError(
                    'Managed plugin installation found but its ID '
                    'does not match the ID of the plugin currently '
                    'on the manager. [existing: {0}, new: {1}]'
                    .format(existing_plugin_id, plugin_id))
        else:
            raise exceptions.PluginInstallationError(
                'Managed plugin installation found but it is '
                'in a corrupted state. [{0}]'.format(plugin_id))


def _get_plugin_description(managed_plugin):
    fields = ['package_name',
              'package_version',
              'supported_platform',
              'distribution',
              'distribution_release']
    return ', '.join('{0}: {1}'.format(
        field, managed_plugin.get(field))
        for field in fields if managed_plugin.get(field))


def _install_managed_plugin(managed_plugin, args):
    dst_dir = target_plugin_prefix(
        name=managed_plugin.package_name,
        tenant_name=ctx.tenant_name,
        version=managed_plugin.package_version
    )
    with _lock(dst_dir):
        if is_already_installed(dst_dir, managed_plugin.id):
            ctx.logger.info(
                'Using existing installation of managed plugin: %s [%s]',
                managed_plugin.id, _get_plugin_description(managed_plugin))
            return

        ctx.logger.info(
            'Installing managed plugin: %s [%s]',
            managed_plugin.id, _get_plugin_description(managed_plugin))
        _make_virtualenv(dst_dir)
        try:
            _wagon_install(plugin=managed_plugin, venv=dst_dir, args=args)
            with open(os.path.join(dst_dir, 'plugin.id'), 'w') as f:
                f.write(managed_plugin.id)
        except Exception as e:
            _rmtree(dst_dir)
            tpe, value, tb = sys.exc_info()
            exc = NonRecoverableError(
                'Failed installing managed plugin: {0} [{1}][{2}]'
                .format(managed_plugin.id, managed_plugin, e))
            reraise(NonRecoverableError, exc, tb)


def _wagon_install(plugin, venv, args):
    client = get_rest_client()
    wagon_dir = tempfile.mkdtemp(prefix='{0}-'.format(plugin.id))
    wagon_path = os.path.join(wagon_dir, 'wagon.tar.gz')
    try:
        ctx.logger.debug('Downloading plugin %s from manager into %s',
                         plugin.id, wagon_path)
        client.plugins.download(plugin_id=plugin.id,
                                output_file=wagon_path)
        ctx.logger.debug('Installing plugin %s using wagon', plugin.id)
        wagon.install(
            wagon_path,
            ignore_platform=True,
            install_args=args,
            venv=venv
        )
    finally:
        ctx.logger.debug('Removing directory: %s', wagon_dir)
        _rmtree(wagon_dir)


def _install_source_plugin(deployment_id, plugin, source, args):
    name = plugin.get('package_name') or plugin['name']
    dst_dir = target_plugin_prefix(
        name=name,
        tenant_name=ctx.tenant_name,
        version=plugin.get('package_version'),
        deployment_id=deployment_id
    )
    with _lock(dst_dir):
        if is_already_installed(dst_dir, 'source-{0}'.format(deployment_id)):
            ctx.logger.info(
                'Using existing installation of source plugin: %s', plugin)
            return

        ctx.logger.info('Installing plugin from source: %s', name)
        _make_virtualenv(dst_dir)
        try:
            _pip_install(source=source, venv=dst_dir, args=args)
        except Exception:
            _rmtree(dst_dir)
            raise
        with open(os.path.join(dst_dir, 'plugin.id'), 'w') as f:
            f.write('source-{0}'.format(deployment_id))


def _pip_install(source, venv, args):
    plugin_dir = None
    try:
        if os.path.isabs(source):
            plugin_dir = source
        else:
            ctx.logger.debug('Extracting archive: %s', source)
            plugin_dir = extract_package_to_dir(source)
        package_name = extract_package_name(plugin_dir)
        ctx.logger.debug('Installing from directory: %s '
                         '[args=%s, package_name=%s]',
                         plugin_dir, args, package_name)
        command = [
            get_python_path(venv), '-m', 'pip', 'install'
        ] + args + [plugin_dir]

        runner.run(command=command, cwd=plugin_dir)
        ctx.logger.debug('Retrieved package name: %s', package_name)
    except CommandExecutionException as e:
        ctx.logger.debug('Failed running pip install. Output:\n%s', e.output)
        raise exceptions.PluginInstallationError(
            'Failed running pip install. ({0})'.format(e.error))
    finally:
        if plugin_dir and not os.path.isabs(source):
            ctx.logger.debug('Removing directory: %s', plugin_dir)
            _rmtree(plugin_dir)


def uninstall(plugin, deployment_id=None):
    name = plugin.get('package_name') or plugin['name']
    dst_dir = target_plugin_prefix(
        name=name,
        tenant_name=ctx.tenant_name,
        version=plugin['package_version'],
        deployment_id=deployment_id
    )
    ctx.logger.info('uninstalling %s', dst_dir)
    if os.path.isdir(dst_dir):
        _rmtree(dst_dir)
    lock_file = '{0}.lock'.format(dst_dir)
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise


def _create_plugins_dir_if_missing():
    plugins_dir = os.path.join(VIRTUALENV, 'plugins')
    if not os.path.exists(plugins_dir):
        try:
            os.makedirs(plugins_dir)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise


@contextmanager
def _lock(path):
    # lock with both a regular threading lock - for multithreaded access,
    # and fasteners lock for multiprocess access
    with PLUGIN_INSTALL_LOCK:
        with fasteners.InterProcessLock('{0}.lock'.format(path)):
            yield


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
        command = [get_python_path(VIRTUALENV), '-m', 'pip', 'download', '-d',
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


def _assert_list_len(lst, expected_len, package_url, archive_dir):
    if len(lst) != expected_len:
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
    plugins.sort(key=lambda plugin: parse_version(plugin['package_version']),
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


def wait_for_wagon_in_directory(plugin_id, retries=30, interval=1):
    path = os.path.join(MANAGER_PLUGINS_PATH, plugin_id)
    for _ in range(retries):
        if os.path.isdir(path) and \
                (any(File.endswith('.wgn') for File in os.listdir(path))):
            return
        time.sleep(interval)


def _link_virtualenv(venv):
    """Add current venv's libs to the target venv.

    Add a .pth file with a link to the current venv, to the target
    venv's site-packages.
    Also copy .pth files' contents from the current venv, so that the
    target venv also uses editable packages from the source venv.
    """
    own_site_packages = get_pth_dir()
    target = get_pth_dir(venv)
    with open(os.path.join(target, 'agent.pth'), 'w') as agent_link:
        agent_link.write('# link to the agent virtualenv, created by '
                         'the plugin installer\n')
        agent_link.write('{0}\n'.format(own_site_packages))

        for filename in glob.glob(os.path.join(own_site_packages, '*.pth')):
            pth_path = os.path.join(own_site_packages, filename)
            with open(pth_path) as pth:
                agent_link.write('\n# copied from {0}:\n'.format(pth_path))
                agent_link.write(pth.read())
                agent_link.write('\n')


def get_pth_dir(venv=None):
    """Get the directory suitable for .pth files in this venv.

    This will return the site-packages directory, which is one of the
    targets that is scanned for .pth files.
    This is mostly a reimplementation of sysconfig.get_path('purelib'),
    but sysconfig is not available in 2.6.
    """
    output = runner.run([
        get_python_path(venv) if venv else sys.executable,
        '-c',
        'import json, sys; print(json.dumps([sys.prefix, sys.version[:3]]))'
    ]).std_out
    prefix, version = json.loads(output)
    if os.name == 'nt':
        return '{0}/Lib/site-packages'.format(prefix)
    elif os.name == 'posix':
        return '{0}/lib/python{1}/site-packages'.format(prefix, version)
    else:
        raise NonRecoverableError('Unsupported OS: {0}'.format(os.name))
