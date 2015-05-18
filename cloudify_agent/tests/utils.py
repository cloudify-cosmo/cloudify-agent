#########
# Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
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
import filecmp
import tarfile
from contextlib import contextmanager

from cloudify.utils import LocalCommandRunner

from cloudify_agent.api import utils

from cloudify_agent.tests import resources


@contextmanager
def env(key, value):
    os.environ[key] = value
    yield
    del os.environ[key]


def create_plugin_tar(plugin_dir_name, target_directory):

    """
    Create a tar file from the plugin.

    :param plugin_dir_name: the plugin directory name, relative to the
    resources package.
    :type plugin_dir_name: str
    :param target_directory: the directory to create the tar in
    :type target_directory: str

    :return: the name of the create tar, note that this is will just return
    the base name, not the full path to the tar.
    :rtype: str
    """

    plugin_source_path = resources.get_resource(os.path.join(
        'plugins', plugin_dir_name))

    plugin_tar_file_name = '{0}.tar'.format(plugin_dir_name)
    target_tar_file_path = os.path.join(target_directory,
                                        plugin_tar_file_name)

    plugin_tar_file = tarfile.TarFile(target_tar_file_path, 'w')
    plugin_tar_file.add(plugin_source_path, plugin_dir_name)
    plugin_tar_file.close()
    return plugin_tar_file_name


def are_dir_trees_equal(dir1, dir2):

    """
    Compare two directories recursively. Files in each directory are
    assumed to be equal if their names and contents are equal.

    :param dir1: First directory path
    :type dir1: str
    :param dir2: Second directory path
    :type dir2: str

    :return: True if the directory trees are the same and
             there were no errors while accessing the directories or files,
             False otherwise.
    :rtype: bool
   """

    # compare file lists in both dirs. If found different lists
    # or "funny" files (failed to compare) - return false
    dirs_cmp = filecmp.dircmp(dir1, dir2)
    if len(dirs_cmp.left_only) > 0 or len(dirs_cmp.right_only) > 0 or \
            len(dirs_cmp.funny_files) > 0:
        return False

    # compare the common files between dir1 and dir2
    (match, mismatch, errors) = filecmp.cmpfiles(
        dir1, dir2, dirs_cmp.common_files, shallow=False)
    if len(mismatch) > 0 or len(errors) > 0:
        return False

    # continue to compare sub-directories, recursively
    for common_dir in dirs_cmp.common_dirs:
        new_dir1 = os.path.join(dir1, common_dir)
        new_dir2 = os.path.join(dir2, common_dir)
        if not are_dir_trees_equal(new_dir1, new_dir2):
            return False

    return True


def uninstall_package_if_exists(package_name):

    """
    Uninstalls a pip package if it exists in the virtualenv

    :param package_name: the pip package name
    :type package_name: str

    """
    runner = LocalCommandRunner()

    out = runner.run('{0} list'.format(utils.get_pip_path())).output
    if package_name in out:
        runner.run('{0} uninstall -y {1}'.format(
            utils.get_pip_path(), package_name), stdout_pipe=False)


def install_package(package_path):

    """
    Installs a pip package to the virtualenv

    :param package_path: the pip package path
    :type package_path: str
    """

    runner = LocalCommandRunner()

    runner.run(
        '{0} install {1}'
        .format(utils.get_pip_path(), package_path),
        stdout_pipe=False)
