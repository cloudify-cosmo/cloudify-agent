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

import uuid
import json
import copy
import tempfile
import sys
import shutil
import os
import pip
import pkg_resources
from jinja2 import Template

from cloudify.utils import LocalCommandRunner
from cloudify.utils import setup_logger
from cloudify.utils import get_home_dir
from cloudify import exceptions

import cloudify_agent
from cloudify_agent import VIRTUALENV
from cloudify_agent.api import plugins
from cloudify_agent.api import defaults

logger = setup_logger('cloudify_agent.api.utils')


def get_agent_stats(name, celery):

    """
    Query for agent stats based on agent name.

    :param name: the agent name
    :type name: str
    :param celery: the celery client to use
    :type celery: celery.Celery

    :return: agents stats
    :rtype: dict

    """

    destination = 'celery@{0}'.format(name)
    inspect = celery.control.inspect(
        destination=[destination])
    stats = (inspect.stats() or {}).get(destination)
    return stats


def get_storage_directory():

    """
    Retrieve path to the directory where all daemon
    properties will be stored.

    :return: path to the directory
    :rtype str

    """
    return os.path.join(get_home_dir(), '.cfy-agent')


def daemon_to_dict(daemon):

    """
    Return a json representation of the daemon. This will remove return all
    the daemon attributes except for the 'celery', 'logger' and 'runner',
    which are not JSON serializable.

    :param daemon: the daemon to serialize.
    :type daemon: cloudify_agent.api.pm.base.Daemon

    :return: a JSON serializable dictionary.
    :rtype: dict

    """

    attr = getattr(daemon, '__dict__')
    if not attr:
        raise ValueError('Cannot save a daemon with no __dict__ attribute.')

    # don't use deepcopy here because we this will try to copy
    # the internal non primitive attributes
    result = copy.copy(daemon.__dict__)
    result.pop('celery')
    result.pop('runner')
    result.pop('logger')
    return result


def generate_agent_name():

    """
    Generates a unique name with a pre-defined prefix

    :return: an agent name
    :rtype: str

    """

    return '{0}-{1}'.format(
        defaults.CLOUDIFY_AGENT_PREFIX,
        uuid.uuid4())


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


def get_full_resource_path(resource_path):
    return pkg_resources.resource_filename(
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
        resource_path='disable-requiretty.sh'
    )
    runner.run('chmod +x {0}'.format(disable_requiretty_script_path))
    runner.run('{0}'.format(disable_requiretty_script_path))


def fix_virtualenv():

    """
    This method is used for auto-configuration of the virtualenv.
    It is needed in case the environment was created using different paths
    than the one that is used at runtime.

    """

    bin_dir = '{0}/bin'.format(VIRTUALENV)

    logger.debug('Searching for executable files in {0}'.format(bin_dir))
    for executable in os.listdir(bin_dir):
        path = os.path.join(bin_dir, executable)
        logger.debug('Checking {0}...'.format(path))
        if not os.path.isfile(path):
            logger.debug('{0} is not a file. Skipping...'.format(path))
            continue
        if os.path.islink(path):
            logger.debug('{0} is a link. Skipping...'.format(path))
            continue
        basename = os.path.basename(path)
        if basename in ['python', 'python2.7', 'python2.6']:
            logger.debug('{0} is the python executable. Skipping...'
                         .format(path))
            continue
        with open(path) as f:
            lines = f.read().split(os.linesep)
            if lines[0].endswith('/bin/python'):
                new_line = '#!{0}/python'.format(bin_dir)
                logger.debug('Replacing {0} with {1}'
                             .format(lines[0], new_line))
                lines[0] = new_line
        with open(path, 'w') as f:
            f.write(os.linesep.join(lines))

    runner = LocalCommandRunner(logger)

    logger.debug('Searching for links in {0}'.format(VIRTUALENV))
    for link in ['archives', 'bin', 'include', 'lib']:
        link_path = '{0}/local/{1}'.format(VIRTUALENV, link)
        logger.debug('Checking {0}...'.format(link_path))
        try:
            runner.run('unlink {0}'.format(link_path))
            runner.run('ln -s {0}/{1} {2}'
                       .format(VIRTUALENV, link, link_path))
        except exceptions.CommandExecutionException:
            pass


def parse_pip_version(pip_version=''):

    """
    Parses a pip version string to identify major, minor, micro versions.

    :param pip_version: the version of pip
    :type pip_version: str

    :return: major, minor, micro version of pip
    :rtype: tuple
    """

    if not pip_version:
        try:
            pip_version = pip.__version__
        except AttributeError as e:
            raise exceptions.NonRecoverableError(
                'Failed to get pip version: ', str(e))

    if not isinstance(pip_version, basestring):
        raise exceptions.NonRecoverableError(
            'Invalid pip version: {0} is not a string'
            .format(pip_version))

    if not pip_version.__contains__("."):
        raise exceptions.NonRecoverableError(
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
        raise exceptions.NonRecoverableError(
            'Invalid pip version: "{0}", major version is "{1}" '
            'while expected to be a number'
            .format(pip_version, major))

    if not str(minor).isdigit():
        raise exceptions.NonRecoverableError(
            'Invalid pip version: "{0}", minor version is "{1}" while '
            'expected to be a number'
            .format(pip_version, minor))

    return major, minor, micro


def extract_package_to_dir(package_url):

    """
    Extracts a pip package to a temporary directory.

    :param package_url: the URL to the package source.
    :type package_url: str

    :return: the directory the package was extracted to.
    :rtype: str
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
        raise exceptions.NonRecoverableError(
            'Failed to download and unpack package from {0}: {1}'
            .format(package_url, str(e)))

    return plugin_dir


def is_pip6_or_higher(pip_version=None):

    """
    Determines if the pip version passed is higher than version 6.

    :param pip_version: the version of pip
    :type pip_version: str

    :return: whether or not the version is higher than version 6.
    :rtype: bool
    """

    major, minor, micro = parse_pip_version(pip_version)
    if int(major) >= 6:
        return True
    else:
        return False


def extract_package_name(package_dir):

    """
    Detects the package name of the package located at 'package_dir' as
    specified in the package setup.py file.

    :param package_dir: the directory the package was extracted to.
    :type package_dir: str

    :return: the package name
    :rtype: str
    """
    runner = LocalCommandRunner()
    plugin_name = runner.run(
        '{0} {1} {2}'.format(
            sys.executable,
            os.path.join(os.path.dirname(plugins.__file__),
                         'extract_package_name.py'),
            package_dir),
        cwd=package_dir
    ).output
    return plugin_name


def list_plugin_files(plugin_name):

    """
    Retrieves python files related to the plugin.
    __init__ file are filtered out.

    :param plugin_name: The plugin name.
    :type plugin_name: string

    :return: A list of file paths.
    :rtype: list of str
    """

    module_paths = []
    runner = LocalCommandRunner(logger)

    files = runner.run(
        '{0} show -f {1}'
        .format(get_pip_path(), plugin_name)
    ).output.splitlines()
    for module in files:
        if module.endswith('.py') and '__init__' not in module:
            # the files paths are relative to the
            # package __init__.py file.
            prefix = '../' if os.name == 'posix' else '..\\'
            module_paths.append(
                module.replace(prefix, '')
                .replace(os.sep, '.').replace('.py', '').strip())
    return module_paths


def dict_to_options(dictionary):

    """
    Transform a dictionary into an options string. any key value pair
    will be translated into the --key=value option.

    :param dictionary: the options dictionary
    :type dictionary: dict

    :return: the options string representing the dictionary
    :rtype: str

    """

    options_string = ''
    for key, value in dictionary.iteritems():
        key = key.replace('_', '-')
        option = '--{0}={1}'.format(key, value)
        options_string = '{0} {1}'.format(options_string, option)
    return options_string.lstrip()


def get_cfy_agent_path():

    """
    Lookup the path to the cfy-agent executable, os agnostic

    :return: path to the cfy-agent executable
    :rtype: str
    """

    if os.name == 'posix':
        return '{0}/bin/cfy-agent'.format(VIRTUALENV)
    else:
        return '{0}\\Scripts\\cfy-agent'.format(VIRTUALENV)


def get_pip_path():

    """
    Lookup the path to the pip executable, os agnostic

    :return: path to the pip executable
    :rtype: str
    """

    if os.name == 'posix':
        return '{0}/bin/pip'.format(VIRTUALENV)
    else:
        return '{0}\\Scripts\\pip'.format(VIRTUALENV)


def get_python_path():

    """
    Lookup the path to the python executable, os agnostic

    :return: path to the python executable
    :rtype: str
    """

    if os.name == 'posix':
        return '{0}/bin/pip'.format(VIRTUALENV)
    else:
        return '{0}\\Scripts\\python'.format(VIRTUALENV)


def env_to_file(env_variables, destination_path=None, posix=True):

    """
    Write environment variables to a file.

    :param env_variables: environment variables
    :type env_variables: dict

    :param destination_path: destination path of a file where the
    environment variables will be stored. the stored variables will be a
    bash script you can then source.
    :type destination_path: str
    :param posix: false if the target of the generated file will be a
    windows machine
    :type posix: bool

    :return: path to the file containing the env variables
    :rtype `str`
    """

    if not env_variables:
        return None
    if not destination_path:
        destination_path = tempfile.mkstemp(suffix='env')[1]

    if posix:
        linesep = '\n'
    else:
        linesep = '\r\n'
    with open(destination_path, 'w') as f:
        if posix:
            f.write('#!/bin/bash')
            f.write('# Environmnet file generated by Cloudify. Do not delete '
                    'unless you know exactly what you are doing.')
            f.write(linesep)
            f.write(linesep)
        else:
            f.write('rem Environmnet file generated by Cloudify. Do not '
                    'delete unless you know exactly what you are doing.')
            f.write(linesep)
        for key, value in env_variables.iteritems():
            if posix:
                f.write('export {0}={1}'.format(key, value))
                f.write(linesep)
            else:
                f.write('set {0}={1}'.format(key, value))
                f.write(linesep)
        f.write(linesep)

    return destination_path


def stringify_values(dictionary):

    """
    Given a dictionary convert all values into the string representation of
    the value. useful for dicts that only allow string values (like os.environ)

    :param dictionary: the dictionary to convert
    :return: a copy of the dictionary where all values are now string.
    :rtype: dict
    """

    dict_copy = copy.deepcopy(dictionary)

    for key, value in dict_copy.iteritems():
        if isinstance(value, dict):
            dict_copy[key] = stringify_values(value)
        else:
            dict_copy[key] = str(value)
    return dict_copy


def purge_none_values(dictionary):

    """
    Given a dictionary remove all key who's value is None.

    :param dictionary: the dictionary to convert
    :return: a copy of the dictionary where no key has a None value
    :rtype: dict
    """

    dict_copy = copy.deepcopy(dictionary)
    for key, value in dictionary.iteritems():
        if dictionary[key] is None:
            del dict_copy[key]
    return dict_copy


def json_load(file_path):

    """
    Loads a JSON file into a dictionary.

    :param file_path: path to the json file
    :type file_path: str

    :return: the dictionary
    :rtype: dict
    """

    logger.debug('Loading JSON from {0}'.format(file_path))
    with open(file_path) as f:
        return json_loads(f.read())


def json_loads(content):

    """
    Loads a JSON string into a dictionary.
    If the string is not a valid json, it will be part
    of the raised exception.


    :param content: the string to load
    :type content: str

    :return: the dictionary
    :rtype: dict
    """

    try:
        return json.loads(content)
    except ValueError as e:
        raise ValueError('{0}:{1}{2}'.format(str(e), os.linesep, content))
