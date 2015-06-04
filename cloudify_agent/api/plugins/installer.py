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
import shutil

from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner

from cloudify_agent.api import utils
from cloudify_agent.api.utils import get_pip_path


class PluginInstaller(object):

    def __init__(self, logger=None):
        self.logger = logger or setup_logger(
            'cloudify_agent.api.plugins.installer')
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
                plugin_dir = utils.extract_package_to_dir(source)
            self.logger.debug('Installing from directory: {0} '
                              '[args={1}]'.format(plugin_dir, args))
            command = '{0} install {1} {2}'.format(
                get_pip_path(), plugin_dir, args)
            self.runner.run(command, cwd=plugin_dir)
            package_name = utils.extract_package_name(plugin_dir)
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
