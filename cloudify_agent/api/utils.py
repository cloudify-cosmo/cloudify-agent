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
import errno
import getpass
import types
import urllib

import appdirs
import pkg_resources

from jinja2 import Template

from cloudify.context import BootstrapContext
from cloudify.constants import SECURED_PROTOCOL
from cloudify.workflows import tasks as workflows_tasks

from cloudify.utils import setup_logger

from cloudify_rest_client import CloudifyClient

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

    @classmethod
    def get_storage_directory(cls, username=None):

        """
        Retrieve path to the directory where all daemon
        registered under a specific username will be stored.
        If no `username` is provided, username under which current daemon
        was installed will be used.

        :param username: the user

        """
        if cls.CLOUDIFY_DAEMON_STORAGE_DIRECTORY_KEY in os.environ:
            return cls.get_daemon_storage_dir()

        if os.name == 'nt':
            return appdirs.site_data_dir('cloudify-agent', 'Cloudify')

        if username is None and cls.CLOUDIFY_DAEMON_USER_KEY in os.environ:
            username = cls.get_daemon_user()
        return os.path.join(get_home_dir(username), '.cfy-agent')

    @staticmethod
    def generate_agent_name():
        """Generates a unique name with a pre-defined prefix
        """
        return '{0}-{1}'.format(defaults.CLOUDIFY_AGENT_PREFIX, uuid.uuid4())

    @staticmethod
    def generate_new_agent_name(old_agent_name):

        """
        Generates a new agent name from old agent name.
        It tries to detect if there is an uuid at the end of the
        `old_agent_name`. If this is the case, this uid is removed.
        Then new uuid is appended to old name.
        :param old_agent_name: name of an old agent

        """

        suffix = str(uuid.uuid4())
        agent_name = old_agent_name
        if len(old_agent_name) > len(suffix):
            old_suffix = old_agent_name[-len(suffix):]
            try:
                uuid.UUID(old_suffix)
                agent_name = old_agent_name[0:-len(suffix)]
                if agent_name.endswith('_'):
                    agent_name = agent_name[:-1]
            except ValueError:
                agent_name = old_agent_name
        new_agent_name = '{0}_{1}'.format(agent_name, suffix)
        if new_agent_name != old_agent_name:
            return new_agent_name
        else:
            return '{0}_{1}'.format(old_agent_name, suffix)

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

    @staticmethod
    def get_broker_configuration(agent):

        client = get_rest_client(
            rest_host=agent['rest_host'],
            rest_port=agent['rest_port'],
            rest_token=agent['rest_token'],
            rest_tenant=agent['rest_tenant'],
            ssl_cert_path=agent['local_rest_cert_file'],
            bypass_maintenance_mode=agent['bypass_maintenance_mode'])

        bootstrap_context_dict = client.manager.get_context()
        bootstrap_context_dict = bootstrap_context_dict['context']['cloudify']
        bootstrap_context = BootstrapContext(bootstrap_context_dict)
        attributes = bootstrap_context.broker_config()
        return attributes

    @staticmethod
    def get_broker_url(agent):
        broker_ip = agent['broker_ip']
        broker_port = agent.get('broker_port', defaults.BROKER_PORT)
        broker_user = agent.get('broker_user', 'guest')
        broker_pass = agent.get('broker_pass', 'guest')
        return defaults.BROKER_URL.format(username=urllib.quote(broker_user),
                                          password=urllib.quote(broker_pass),
                                          host=broker_ip,
                                          port=broker_port)


internal = _Internal()


def get_celery_client(broker_url,
                      broker_ssl_enabled=False,
                      broker_ssl_cert_path=None,
                      max_retries=None):

    # celery is imported locally since it's not used by any other method, and
    # we want this utils module to be usable even if celery is not available
    from celery import Celery

    celery_client = Celery(broker=broker_url,
                           backend=broker_url)
    celery_client.conf.update(
        CELERY_TASK_RESULT_EXPIRES=defaults.CELERY_TASK_RESULT_EXPIRES)

    if broker_ssl_enabled:
        # import always?
        import ssl
        celery_client.conf.BROKER_USE_SSL = {
            'ca_certs': broker_ssl_cert_path,
            'cert_reqs': ssl.CERT_REQUIRED,
        }

    # Connect eagerly to error out as early as possible, and to force choosing
    # the broker if multiple urls were passed.
    # If max_retries is provided and >0, we will raise an exception if we
    # can't connect; otherwise we'll keep retrying forever.
    # Need to raise an exception in the case of a cluster, so that the
    # next node can be tried
    celery_client.pool.connection.ensure_connection(max_retries=max_retries)
    return celery_client


def get_cluster_celery_client(broker_urls, cluster):
    err = None
    for broker_url, node in zip(broker_urls, cluster):
        try:
            return get_celery_client(
                broker_url=broker_url,
                broker_ssl_enabled=node.get('broker_ssl_enabled'),
                broker_ssl_cert_path=node.get('internal_cert_path'),
                max_retries=1)
        except Exception as err:
            continue
    if err is not None:
        raise err


def get_agent_registered(name,
                         celery_client,
                         timeout=workflows_tasks.INSPECT_TIMEOUT):

    """
    Query for agent registered tasks based on agent name.

    :param name: the agent name
    :param celery_client: the celery client to use
    :param timeout: timeout for inspect command

    :return: agents registered tasks
    :rtype: dict

    """

    destination = 'celery@{0}'.format(name)
    inspect = celery_client.control.inspect(
        destination=[destination],
        timeout=timeout)

    registered = inspect.registered()
    if registered is None or destination not in registered:
        return None
    return set(registered[destination])


def get_windows_home_dir(username):
    return 'C:\\Users\\{0}'.format(username)


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
            return get_windows_home_dir(username)
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


def get_bool_or_default(raw_value, default_value):
    if raw_value is None:
        return default_value

    if isinstance(raw_value, types.BooleanType):
        return raw_value
    elif isinstance(raw_value, basestring):
        return raw_value.lower() == 'true'
    else:
        raise ValueError('value has invalid type: {0}, expected boolean or '
                         'string'.format(type(raw_value)))


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


def safe_create_dir(path):
    # creating a dir, ignoring exists error to handle possible race condition
    try:
        os.makedirs(path)
    except OSError as ose:
        if ose.errno != errno.EEXIST:
            raise


def get_rest_client(rest_host,
                    rest_port,
                    rest_token,
                    rest_tenant,
                    ssl_cert_path,
                    bypass_maintenance_mode=False):

    headers = {}
    if bypass_maintenance_mode:
        headers['X-BYPASS-MAINTENANCE'] = 'true'

    for value, name in [(rest_token, 'auth token'),
                        (rest_tenant, 'tenant'),
                        (ssl_cert_path, 'SSL Cert path')]:
        assert value, 'REST {0} is missing! It is required to ' \
                      'create a REST client for a secured ' \
                      'manager [{1}]'.format(name, rest_host)

    return CloudifyClient(
        host=rest_host,
        protocol=SECURED_PROTOCOL,
        port=rest_port,
        headers=headers,
        token=rest_token,
        tenant=rest_tenant,
        cert=ssl_cert_path
    )
