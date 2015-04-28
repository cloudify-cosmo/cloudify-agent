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
import tempfile
import pkg_resources
from jinja2 import Template

from cloudify.utils import LocalCommandRunner
from cloudify.utils import setup_logger
from cloudify.exceptions import CommandExecutionException

import cloudify_agent
from cloudify_agent import VIRTUALENV


logger = setup_logger('cloudify_agent.api.utils')


def render_template_to_file(template_path, file_path=None, **values):

    """
    Render a 'jinja' template resource to a temporary file.

    :param template_path: relative path to the template.
    :type template_path: str

    :param file_path: absolute path to the desired output file.
    :type file_path: str

    :param values: keyword arguments passed to jinja.
    :type values: dict

    :return path to the temporary file.
    :rtype `str`
    """

    template = get_resource(template_path)
    rendered = Template(template).render(**values)
    return content_to_file(rendered, file_path)


def resource_to_tempfile(resource_path):

    """
    Copy a resource into a temporary file.

    :param resource_path: relative path to the resource.
    :type resource_path: str

    :return path to the temporary file.
    :rtype `str`
    """

    resource = get_resource(resource_path)
    return content_to_file(resource)


def get_resource(resource_path):

    """
    Loads the resource into a string.

    :param resource_path: relative path to the resource.
    :type resource_path: str

    :return the resource as a string.
    :rtype `str`
    """

    return pkg_resources.resource_string(
        cloudify_agent.__name__,
        os.path.join('resources', resource_path)
    )


def content_to_file(content, file_path=None):

    """
    Write string to a temporary file.

    :param content:
    :type content: str

    :param file_path: absolute path to the desired output file.
    :type file_path: str

    :return path to the temporary file.
    :rtype `str`
    """

    if not file_path:
        file_path = tempfile.NamedTemporaryFile(mode='w', delete=False).name
    with open(file_path, 'w') as f:
        f.write(content)
        f.write(os.linesep)
    return file_path


def disable_requiretty():

    """
    Disables the requiretty directive in the /etc/sudoers file. This
    will enable operations that require sudo permissions to work properly.

    This is needed because operations are executed
    from within the worker process, which is not a tty process.

    """

    runner = LocalCommandRunner(logger)

    disable_requiretty_script_path = resource_to_tempfile(
        resource_path='initd/disable-requiretty.sh'
    )
    runner.run('chmod +x {0}'.format(disable_requiretty_script_path))
    runner.sudo('{0}'.format(disable_requiretty_script_path))


def fix_virtualenv():

    """
    This method is used for auto-configuration of the virtualenv.
    It is needed in case the environment was created using different paths
    than the one that is used at runtime.

    """

    bin_dir = '{0}/bin'.format(VIRTUALENV)

    for executable in os.listdir(bin_dir):
        path = os.path.join(bin_dir, executable)
        if not os.path.isfile(path):
            continue
        if os.path.islink(path):
            continue
        basename = os.path.basename(path)
        if basename in ['python', 'python2.7', 'python2.6']:
            continue
        with open(path) as f:
            lines = f.read().split(os.linesep)
            if lines[0].endswith('/bin/python'):
                lines[0] = '#!{0}/python'.format(bin_dir)
        with open(path, 'w') as f:
            f.write(os.linesep.join(lines))

    runner = LocalCommandRunner(logger)

    for link in ['archives', 'bin', 'include', 'lib']:
        link_path = '{0}/local/{1}'.format(VIRTUALENV, link)
        try:
            runner.run('unlink {0}'.format(link_path))
            runner.run('ln -s {0}/{1} {2}'
                       .format(VIRTUALENV, link, link_path))
        except CommandExecutionException:
            pass


def env_to_file(env_variables, destination_path=None):

    """

    :param env_variables: environment variables
    :type env_variables: dict

    :param destination_path: destination path of a file where the
    environment variables will be stored. the stored variables will be a
    bash script you can then source.
    :type destination_path: str

    :return: path to the file containing the env variables
    :rtype `str`
    """

    if not destination_path:
        destination_path = tempfile.mkstemp(suffix='env')[1]

    with open(destination_path, 'a') as f:
        f.write('# This file was generated by cloudify. Do not delete!')
        f.write(os.linesep)
        for key, value in env_variables.iteritems():
            f.write('export {0}={1}'.format(key, value))
            f.write(os.linesep)

    return destination_path
