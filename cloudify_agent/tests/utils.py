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

import logging
import platform
import time
import socket
import subprocess
import os
import filecmp
import tarfile
import uuid
from contextlib import contextmanager

from wagon import wagon
from agent_packager import packager

from cloudify.exceptions import NonRecoverableError
from cloudify.utils import LocalCommandRunner
from cloudify.utils import setup_logger

import cloudify_agent

from cloudify_agent import VIRTUALENV
from cloudify_agent.tests import resources

logger = setup_logger('cloudify_agent.tests.utils')


@contextmanager
def env(key, value):
    os.environ[key] = value
    yield
    del os.environ[key]


def create_mock_plugin(basedir, install_requires=None):
    install_requires = install_requires or []
    name = str(uuid.uuid4())
    plugin_dir = os.path.join(basedir, name)
    setup_py = os.path.join(plugin_dir, 'setup.py')
    os.mkdir(plugin_dir)
    with open(setup_py, 'w') as f:
        f.write('from setuptools import setup; '
                'setup(name="{0}", install_requires={1}, version="0.1")'
                .format(name, install_requires))
    return name


def create_plugin_tar(plugin_dir_name,
                      target_directory,
                      basedir=None):

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

    if basedir:
        plugin_source_path = os.path.join(basedir, plugin_dir_name)
    else:
        plugin_source_path = resources.get_resource(os.path.join(
            'plugins', plugin_dir_name))

    plugin_tar_file_name = '{0}.tar'.format(plugin_dir_name)
    target_tar_file_path = os.path.join(target_directory,
                                        plugin_tar_file_name)

    plugin_tar_file = tarfile.TarFile(target_tar_file_path, 'w')
    try:
        plugin_tar_file.add(plugin_source_path, plugin_dir_name)
    finally:
        plugin_tar_file.close()

    return plugin_tar_file_name


def create_plugin_wagon(plugin_dir_name,
                        target_directory,
                        requirements=False,
                        basedir=None):

    """
    Create a wagon from a plugin.

    :param plugin_dir_name: the plugin directory name, relative to the
    resources package.
    :type plugin_dir_name: str
    :param target_directory: the directory to create the wagon in
    :type target_directory: str
    :param requirements: optional requirements for wagon
    :type requirements: str

    :return: path to created wagon`
    :rtype: str
    """
    if basedir:
        plugin_source_path = os.path.join(basedir, plugin_dir_name)
    else:
        plugin_source_path = resources.get_resource(os.path.join(
            'plugins', plugin_dir_name))
    w = wagon.Wagon(plugin_source_path)
    return w.create(with_requirements=requirements,
                    archive_destination_dir=target_directory)


def get_source_uri():
    return os.path.dirname(os.path.dirname(cloudify_agent.__file__))


def get_requirements_uri():
    return os.path.join(get_source_uri(), 'dev-requirements.txt')


# This should be integrated into packager
# For now, this is the best place
def create_windows_installer(config, logger):
    runner = LocalCommandRunner()
    wheelhouse = resources.get_resource('winpackage/source/wheels')

    pip_cmd = 'pip wheel --wheel-dir {wheel_dir} --requirement {req_file}'.\
        format(wheel_dir=wheelhouse, req_file=config['requirements_file'])

    logger.info('Building wheels into: {0}'.format(wheelhouse))
    runner.run(pip_cmd)

    pip_cmd = 'pip wheel --find-links {wheel_dir} --wheel-dir {wheel_dir} ' \
              '{repo_url}'.format(wheel_dir=wheelhouse,
                                  repo_url=config['cloudify_agent_module'])
    runner.run(pip_cmd)

    iscc_cmd = 'C:\\Program Files (x86)\\Inno Setup 5\\iscc.exe {0}'\
        .format(resources.get_resource(
            os.path.join('winpackage', 'create.iss')))
    os.environ['VERSION'] = '0'
    os.environ['iscc_output'] = os.getcwd()
    runner.run(iscc_cmd)


def create_agent_package(directory, config, package_logger=None):
    if package_logger is None:
        package_logger = logger
    package_logger.info('Changing directory into {0}'.format(directory))
    original = os.getcwd()
    try:
        package_logger.info('Creating Agent Package')
        os.chdir(directory)
        if platform.system() == 'Linux':
            packager.create(config=config,
                            config_file=None,
                            force=False,
                            verbose=False)
            distname, _, distid = platform.dist()
            return '{0}-{1}-agent.tar.gz'.format(distname, distid)
        elif platform.system() == 'Windows':
            create_windows_installer(config, logger)
            return 'cloudify_agent_0.exe'
        else:
            raise NonRecoverableError('Platform not supported: {0}'
                                      .format(platform.system()))
    finally:
        os.chdir(original)


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


class FileServer(object):

    def __init__(self, root_path=None, port=5555):
        self.port = port
        self.root_path = root_path or os.path.dirname(resources.__file__)
        self.process = None
        self.logger = setup_logger('cloudify_agent.tests.utils.FileServer',
                                   logger_level=logging.DEBUG)
        self.runner = LocalCommandRunner(self.logger)

    def start(self, timeout=5):
        if os.name == 'nt':
            serve_path = os.path.join(VIRTUALENV, 'Scripts', 'serve')
        else:
            serve_path = os.path.join(VIRTUALENV, 'bin', 'serve')

        self.process = subprocess.Popen(
            [serve_path, '-p', str(self.port), self.root_path],
            stdin=open(os.devnull, 'w'),
            stdout=None,
            stderr=None)

        end_time = time.time() + timeout

        while end_time > time.time():
            if self.is_alive():
                logger.info('File server is up and serving from {0} ({1})'
                            .format(self.root_path, self.process.pid))
                return
            logger.info('File server is not responding. waiting 10ms')
            time.sleep(0.1)
        raise RuntimeError('FileServer failed to start')

    def stop(self, timeout=15):
        if self.process is None:
            return

        end_time = time.time() + timeout

        if os.name == 'nt':
            self.runner.run('taskkill /F /T /PID {0}'.format(self.process.pid),
                            stdout_pipe=False, stderr_pipe=False,
                            exit_on_failure=False)
        else:
            self.runner.run('kill -9 {0}'.format(self.process.pid))

        while end_time > time.time():
            if not self.is_alive():
                logger.info('File server has shutdown')
                return
            logger.info('File server is still running. waiting 10ms')
            time.sleep(0.1)
        raise RuntimeError('FileServer failed to stop')

    def is_alive(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(('localhost', self.port))
            s.close()
            return True
        except socket.error:
            return False


def op_context(task_name,
               task_target='non-empty-value',
               deployment_id=None,
               plugin_name=None,
               package_name=None,
               package_version=None,
               execution_env=None,
               tenant_name='default_tenant'):
    result = {
        'type': 'operation',
        'task_name': task_name,
        'task_target': task_target,
        'tenant_name': tenant_name,
        'execution_env': execution_env,
        'plugin': {
            'name': plugin_name,
            'package_name': package_name,
            'package_version': package_version
        }
    }
    if deployment_id:
        result['deployment_id'] = deployment_id
    return result
