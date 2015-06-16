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
import pip
import shutil
import tempfile

from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner

from cloudify_agent.api import utils
from cloudify_agent.api import plugins
from cloudify_agent.api.utils import get_pip_path
from cloudify_agent.api import errors


class PluginInstaller(object):

    def __init__(self, logger=None):
        self.logger = logger or setup_logger(self.__class__.__name__)
        self.runner = LocalCommandRunner(logger=self.logger)

    def install(self, source, args=''):

        """
        Install the plugin to the current virtualenv.

        :param source: URL to the plugin. Any pip acceptable URL is ok.
        :param args: extra installation arguments passed to the pip command
        """

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
                shutil.rmtree(plugin_dir)

        return package_name

    def uninstall(self, package_name, ignore_missing=True):

        """
        Uninstall the plugin from the current virtualenv. By default this
        operation will fail when trying to uninstall a plugin that is not
        installed, use `ignore_missing` to change this behavior.

        :param package_name: the package name as stated in the setup.py file
        :param ignore_missing: ignore failures in uninstalling missing plugins.
        """

        if not ignore_missing:
            self.runner.run('{0} uninstall -y {1}'.format(
                utils.get_pip_path(), package_name))
        else:
            out = self.runner.run(
                '{0} freeze'.format(utils.get_pip_path())).std_out
            packages = []
            for line in out.splitlines():
                packages.append(line.split('==')[0])
            if package_name in packages:
                self.runner.run('{0} uninstall -y {1}'.format(
                    utils.get_pip_path(), package_name))
            else:
                self.logger.info('{0} not installed. Nothing to do'
                                 .format(package_name))


def extract_package_to_dir(package_url):

    """
    Extracts a pip package to a temporary directory.

    :param package_url: the URL to the package source.

    :return: the directory the package was extracted to.
    """

    plugin_dir = None

    try:
        plugin_dir = tempfile.mkdtemp()
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
        raise errors.PluginInstallationError(
            'Failed to download and unpack package from {0}: {1}'
            .format(package_url, str(e)))

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
            raise errors.PluginInstallationError(
                'Failed to get pip version: ', str(e))

    if not isinstance(pip_version, basestring):
        raise errors.PluginInstallationError(
            'Invalid pip version: {0} is not a string'
            .format(pip_version))

    if not pip_version.__contains__("."):
        raise errors.PluginInstallationError(
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
        raise errors.PluginInstallationError(
            'Invalid pip version: "{0}", major version is "{1}" '
            'while expected to be a number'
            .format(pip_version, major))

    if not str(minor).isdigit():
        raise errors.PluginInstallationError(
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
