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

import uuid
import json
import copy
import tempfile
import os
import getpass
import pkg_resources
from jinja2 import Template

from cloudify.utils import setup_logger

import cloudify_agent
from cloudify_agent import VIRTUALENV
from cloudify_agent.api import defaults

logger = setup_logger('cloudify_agent.api.utils')


class _Internal(object):

    """
    Contains various internal utility methods. Import this at your own
    peril, as backwards compatibility is not guaranteed.
    """

    CLOUDIFY_DAEMON_NAME_KEY = 'CLOUDIFY_DAEMON_NAME'
    CLOUDIFY_DAEMON_STORAGE_DIRECTORY_KEY = 'CLOUDIFY_DAEMON_STORAGE_DIRECTORY'
    CLOUDIFY_DAEMON_USER_KEY = 'CLOUDIFY_DAEMON_USER'

    @classmethod
    def get_daemon_name(cls):

        """
        Returns the name of the currently running daemon.
        """

        return os.environ[cls.CLOUDIFY_DAEMON_NAME_KEY]

    @classmethod
    def get_daemon_storage_dir(cls):

        """
        Returns the storage directory the current daemon is stored under.
        """

        return os.environ[cls.CLOUDIFY_DAEMON_STORAGE_DIRECTORY_KEY]

    @classmethod
    def get_daemon_user(cls):

        """
        Return the user the current daemon is running under
        """

        return os.environ[cls.CLOUDIFY_DAEMON_USER_KEY]

    @staticmethod
    def get_storage_directory(username=None):

        """
        Retrieve path to the directory where all daemon
        registered under a specific username will be stored.

        :param username: the user

        """

        return os.path.join(get_home_dir(username), '.cfy-agent')

    @staticmethod
    def generate_agent_name():

        """
        Generates a unique name with a pre-defined prefix

        """

        return '{0}-{1}'.format(
            defaults.CLOUDIFY_AGENT_PREFIX,
            uuid.uuid4())

    @staticmethod
    def daemon_to_dict(daemon):

        """
        Return a json representation of the daemon by copying the __dict__
        attribute value. Also notice that this implementation removes any
        attributes starting with the underscore ('_') character.

        :param daemon: the daemon.
        :type daemon: cloudify_agent.api.pm.base.Daemon
        """

        try:
            getattr(daemon, '__dict__')
        except AttributeError:
            raise ValueError('Cannot save a daemon with '
                             'no __dict__ attribute.')

        # don't use deepcopy here because we this will try to copy
        # the internal non primitive attributes
        original = daemon.__dict__
        result = copy.copy(original)
        for attr in original:
            if attr.startswith('_'):
                result.pop(attr)
        return result


internal = _Internal()


def get_agent_registered(name, celery):

    """
    Query for agent registered tasks based on agent name.

    :param name: the agent name
    :param celery: the celery client to use

    :return: agents registered tasks
    :rtype: dict

    """

    destination = 'celery@{0}'.format(name)
    inspect = celery.control.inspect(
        destination=[destination])
    registered = (inspect.registered() or {}).get(destination)
    return registered


def get_home_dir(username=None):

    """
    Retrieve the home directory of the given user. If no user was specified,
    the currently logged user will be used.

    :param username: the user.
    """

    if os.name == 'nt':
        if username is None:
            return os.path.expanduser('~')
        else:
            return os.path.expanduser('~{0}'.format(username))
    else:
        import pwd
        if username is None:
            if 'SUDO_USER' in os.environ:
                # command was executed via sudo
                # get the original user
                username = os.environ['SUDO_USER']
            else:
                username = getpass.getuser()
        return pwd.getpwnam(username).pw_dir


def render_template_to_file(template_path, file_path=None, **values):

    """
    Render a 'jinja' template resource to a temporary file.

    :param template_path: relative path to the template.
    :param file_path: absolute path to the desired output file.
    :param values: keyword arguments passed to jinja.
    """

    template = get_resource(template_path)
    rendered = Template(template).render(**values)
    return content_to_file(rendered, file_path)


def resource_to_tempfile(resource_path):

    """
    Copy a resource into a temporary file.

    :param resource_path: relative path to the resource.

    :return path to the temporary file.
    """

    resource = get_resource(resource_path)
    return content_to_file(resource)


def get_resource(resource_path):

    """
    Loads the resource into a string.

    :param resource_path: relative path to the resource.
    """

    return pkg_resources.resource_string(
        cloudify_agent.__name__,
        os.path.join('resources', resource_path)
    )


def get_absolute_resource_path(resource_path):

    """
    Retrieves the absolute path in the file system of a resource of the
    package.

    :param resource_path: the relative path to the resource
    """
    return pkg_resources.resource_filename(
        cloudify_agent.__name__,
        os.path.join('resources', resource_path)
    )


def content_to_file(content, file_path=None):

    """
    Write string to a temporary file.

    :param content:
    :param file_path: absolute path to the desired output file.
    """

    if not file_path:
        file_path = tempfile.NamedTemporaryFile(mode='w', delete=False).name
    with open(file_path, 'w') as f:
        f.write(content)
        f.write(os.linesep)
    return file_path


def get_executable_path(executable):

    """
    Lookup the path to the executable, os agnostic

    :param executable: the name of the executable
    """

    if os.name == 'posix':
        return '{0}/bin/{1}'.format(VIRTUALENV, executable)
    else:
        return '{0}\\Scripts\\{1}'.format(VIRTUALENV, executable)


def get_cfy_agent_path():

    """
    Lookup the path to the cfy-agent executable, os agnostic

    :return: path to the cfy-agent executable
    """

    return get_executable_path('cfy-agent')


def get_pip_path():

    """
    Lookup the path to the pip executable, os agnostic

    :return: path to the pip executable
    """

    return get_executable_path('pip')


def get_celery_path():

    """
    Lookup the path to the celery executable, os agnostic

    :return: path to the celery executable
    """

    return get_executable_path('celery')


def get_python_path():

    """
    Lookup the path to the python executable, os agnostic

    :return: path to the python executable
    """

    return get_executable_path('python')


def env_to_file(env_variables, destination_path=None, posix=True):

    """
    Write environment variables to a file.

    :param env_variables: environment variables
    :param destination_path: destination path of a file where the
                             environment variables will be stored. the
                             stored variables will be a bash script you can
                             then source.
    :param posix: false if the target of the generated file will be a
                  windows machine

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
            f.write(linesep)
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
    Given a dictionary remove all key who's value is None. Does not purge
    nested values.

    :param dictionary: the dictionary to convert

    :return: a copy of the dictionary where no key has a None value
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
    """

    with open(file_path) as f:
        return json_loads(f.read())


def json_loads(content):

    """
    Loads a JSON string into a dictionary.
    If the string is not a valid json, it will be part
    of the raised exception.


    :param content: the string to load
    """

    try:
        return json.loads(content)
    except ValueError as e:
        raise ValueError('{0}:{1}{2}'.format(str(e), os.linesep, content))
