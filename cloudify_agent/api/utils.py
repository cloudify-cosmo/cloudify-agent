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
import sys
import socket
import struct
import array
import operator

import appdirs

from jinja2 import Template

from cloudify.context import BootstrapContext
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
        if username is None and cls.CLOUDIFY_DAEMON_USER_KEY in os.environ:
            username = cls.get_daemon_user()
        return appdirs.user_data_dir('cloudify-agent', 'Cloudify')

    @staticmethod
    def generate_agent_name():

        """
        Generates a unique name with a pre-defined prefix

        """

        return '{0}-{1}'.format(
            defaults.CLOUDIFY_AGENT_PREFIX,
            uuid.uuid4())

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

        headers = None
        if agent.get('bypass_maintenance_mode'):
            headers = {'X-BYPASS-MAINTENANCE': 'true'}

        client = CloudifyClient(
            agent['manager_ip'],
            agent['manager_port'],
            headers=headers
        )
        bootstrap_context_dict = client.manager.get_context()
        bootstrap_context_dict = bootstrap_context_dict['context']['cloudify']
        bootstrap_context = BootstrapContext(bootstrap_context_dict)
        attributes = bootstrap_context.broker_config(
            fallback_to_manager_ip=False)
        if not attributes.get('broker_ip'):
            attributes['broker_ip'] = agent['manager_ip']
        return attributes

    @staticmethod
    def get_broker_url(agent):
        broker_port = agent.get('broker_port', defaults.BROKER_PORT)
        if agent.get('broker_ip'):
            broker_ip = agent['broker_ip']
        else:
            broker_ip = agent['manager_ip']
        broker_user = agent.get('broker_user', 'guest')
        broker_pass = agent.get('broker_pass', 'guest')
        return defaults.BROKER_URL.format(username=broker_user,
                                          password=broker_pass,
                                          host=broker_ip,
                                          port=broker_port)


internal = _Internal()


def get_celery_client(broker_url,
                      ssl_enabled=False,
                      ssl_cert_path=None):

    # celery is imported locally since it's not used by any other method, and
    # we want this utils module to be usable even if celery is not available
    from celery import Celery

    celery_client = Celery(broker=broker_url,
                           backend=broker_url)
    celery_client.conf.update(
        CELERY_TASK_RESULT_EXPIRES=defaults.CELERY_TASK_RESULT_EXPIRES)
    if ssl_enabled:
        # import always?
        import ssl
        celery_client.conf.BROKER_USE_SSL = {
            'ca_certs': ssl_cert_path,
            'cert_reqs': ssl.CERT_REQUIRED,
        }
    return celery_client


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


class IPExtractor(object):
    @staticmethod
    def get_all_private_ips(sort_ip=None, max_interfaces=128):
        """Returns a list of all the current machine's private IPs (linux only)

        :param sort_ip: If passed, the list of IPs will be sorted by their
        proximity to this IP
        :param max_interfaces: The number of net interfaces on the machine
        """
        struct_size = IPExtractor._get_struct_size()
        bytes_to_read = struct_size * max_interfaces
        buff = array.array('B', '\0' * bytes_to_read)
        bytes_read = IPExtractor._read_bytes(bytes_to_read, buff)
        name_str = buff.tostring()
        ips = IPExtractor._get_ips_from_str(bytes_read, struct_size, name_str)
        if sort_ip:
            return IPExtractor._sort_ips(ips, sort_ip)
        else:
            return ips

    @staticmethod
    def _get_struct_size():
        """Calculate the size of bytes we should read, and the size of
        each struct
        """
        is_64bits = sys.maxsize > 2**32
        return 40 if is_64bits else 32

    @staticmethod
    def _read_bytes(bytes_to_read, buff):
        """Read `bytes_to_read` bytes from a socket into `buff`
        :param bytes_to_read: (Max) number of bytes to read
        :param buff: The buffer into which to read the bytes
        :return: Number of bytes read
        """
        # Importing here to avoid errors on Windows machine (fcntl is only
        # supported on linux), as this piece of code will only ever run on
        # the manager, so there shouldn't be a problem
        import fcntl
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return struct.unpack('iL', fcntl.ioctl(
            s.fileno(),
            # 0x8912 = SIOCGIFCONF - an op to return a list of
            # interface addresses (see man for netdevice)
            0x8912,
            # buffer_info returns a (address, length) tuple
            struct.pack('iL', bytes_to_read, buff.buffer_info()[0])
        ))[0]

    @staticmethod
    def _get_ips_from_str(bytes_read, struct_size, str_buff):
        """Traverse the buffer - split it into `struct_size`d chunks and
        extract the IP address from each chunk
        :param bytes_read: Total length of the buffer
        :param struct_size: Size of each struct
        :param str_buff: A string representation of the buffer
        :return: A list of IP addresses
        """
        ips = []
        for i in range(0, bytes_read, struct_size):
            ip = socket.inet_ntoa(str_buff[i + 20:i + 24])
            if ip != '127.0.0.1':
                ips.append(ip)
        return ips

    @staticmethod
    def _sort_ips(ips, sort_ip):
        """Receive a list of IPs and an IP on which to sort them, and return
        a the list sorted by the proximity of each IP to the sort IP
        """
        # Init all the IPs with zero proximity
        proximity_dict = dict((ip, 0) for ip in ips)
        # Split the IP by `.` - should have 4 parts
        delimited_sort_ip = sort_ip.split('.')
        for ip in ips:
            delimited_ip = ip.split('.')
            # Compare each of the 4 parts - if they're equal, increase the
            # proximity, otherwise - quit the loop (no point in checking
            # after first mismatch)
            for i in range(4):
                if delimited_sort_ip[i] == delimited_ip[i]:
                    proximity_dict[ip] += 1
                else:
                    break
        # Get a list of tuples (IP, proximity) in descending order
        sorted_ips = sorted(proximity_dict.items(),
                            key=operator.itemgetter(1),
                            reverse=True)
        # Return only the IPs
        return [ip[0] for ip in sorted_ips]


get_all_private_ips = IPExtractor.get_all_private_ips
