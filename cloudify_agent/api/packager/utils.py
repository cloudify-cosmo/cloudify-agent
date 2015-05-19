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


import codes
import platform
import sys
import requests
import re
import logging

from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner

logger = setup_logger('cloudify_agent.api.packager.packager')
runner = LocalCommandRunner(logger=logger)


def set_global_verbosity_level(is_verbose_output=False):
    """sets the global verbosity level for console and the lgr logger.
    :param bool is_verbose_output: should be output be verbose
    """
    global verbose_output
    verbose_output = is_verbose_output
    if verbose_output:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)


def make_virtualenv(virtualenv_dir, python='/usr/bin/python'):
    """creates a virtualenv

    :param string virtualenv_dir: path of virtualenv to create
    """
    logger.debug('virtualenv_dir: {0}'.format(virtualenv_dir))
    p = runner.run('virtualenv -p {0} {1}'.format(python, virtualenv_dir))
    if not p.code == 0:
        logger.error('Could not create venv: {0}'.format(virtualenv_dir))
        sys.exit(codes.errors['could_not_create_virtualenv'])


def install_module(module, venv):
    """installs a module in a virtualenv

    :param string module: module to install. can be a url or a path.
    :param string venv: path of virtualenv to install in.
    """
    logger.debug('Installing {0} in venv {1}'.format(module, venv))
    if module == 'pre':
        pip_cmd = '{1}/bin/pip install {0} --pre'.format(module, venv)
    else:
        pip_cmd = '{1}/bin/pip install {0}'.format(module, venv)
    p = runner.run(pip_cmd)
    logger.debug(p.output)
    if not p.code == 0:
        logger.error('Could not install module: {0}'.format(module))
        sys.exit(codes.errors['could_not_install_module'])


def install_requirements_file(path, venv):
    """installs modules from a requirements file in a virtualenv

    :param string path: path to requirements file1
    :param string venv: path of virtualenv to install in
    """
    logger.debug('Installing {0} in venv {1}'.format(path, venv))
    pip_cmd = '{1}/bin/pip install -r{0}'.format(path, venv)
    p = runner.run(pip_cmd)
    logger.debug(p.output)
    if not p.code == 0:
        logger.error('Could not install from requirements file: {0}'.format(
            path))
        sys.exit(codes.errors['could_not_install_from_requirements_file'])


def uninstall_module(module, venv):
    """uninstalls a module from a virtualenv

    :param string module: module to install. can be a url or a path.
    :param string venv: path of virtualenv to install in.
    """
    logger.debug('Uninstalling {0} in venv {1}'.format(module, venv))
    pip_cmd = '{1}/bin/pip uninstall {0} -y'.format(module, venv)
    p = runner.run(pip_cmd)
    if not p.code == 0:
        logger.error('Could not uninstall module: {0}'.format(module))
        sys.exit(codes.errors['could_not_uninstall_module'])


def get_installed(venv):
    p = runner.run('{0}/bin/pip freeze'.format(venv))
    return p.output


def check_installed(module, venv):
    """checks to see if a module is installed

    :param string module: module to install. can be a url or a path.
    :param string venv: path of virtualenv to install in.
    """
    p = runner.run('{0}/bin/pip freeze'.format(venv))
    if re.search(r'{0}'.format(module), p.output.lower()):
        logger.debug('Module {0} is installed in {1}'.format(module, venv))
        return True
    logger.debug('Module {0} is not installed in {1}'.format(module, venv))
    return False


def download_file(url, destination):
    """downloads a file to a destination
    """
    logger.debug('Downloading {0} to {1}...'.format(url, destination))
    destination = destination if destination else url.split('/')[-1]
    r = requests.get(url, stream=True)
    if not r.status_code == 200:
        logger.error('Could not download file: {0}'.format(url))
        sys.exit(codes.errors['could_not_download_file'])
    with open(destination, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()


def tar(source, destination):
    # TODO: solve or depracate..
    # TODO: apparently, it will tar the first child dir of
    # TODO: source, and not the given parent.
    # with closing(tarfile.open(destination, "w:gz")) as tar:
    #     tar.add(source, arcname=os.path.basename(source))
    # WORKAROUND IMPLEMENTATION
    logger.info('Creating tar file: {0}'.format(destination))
    r = runner.run('tar czvf {0} {1}'.format(destination, source))
    if not r.code == 0:
        logger.error('Failed to create tar file.')
        sys.exit(codes.errors['failed_to_create_tar'])


def get_os_props():
        """returns a tuple of the distro and release
        """
        data = platform.dist()
        distro = data[0]
        release = data[2]
        return distro, release
