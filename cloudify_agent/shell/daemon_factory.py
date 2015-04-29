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
import json
import logging

from cloudify.utils import setup_logger

from cloudify_agent.api.pm.base import Daemon
from cloudify_agent.shell import exceptions
from cloudify_agent.shell import errors
from cloudify_agent.shell import utils


logger = setup_logger('cloudify_agent.shell.daemon_factory')


class DaemonFactory(object):

    """
    Factory class for manipulating various daemon instances.

    """

    @staticmethod
    def _find_implementation(process_management):

        """
        Locates the proper daemon implementation for the specific
        process management system. For this to work, all implementations
        need to be imported at this time.

        see api/internal/daemon/__init__.py

        :param process_management: The process management type.
        :type process_management: str

        :raise DaemonNotImplementedError: if no implementation could be found.
        """

        daemons = Daemon.__subclasses__()
        for daemon in daemons:
            if daemon.PROCESS_MANAGEMENT == process_management:
                return daemon
        raise errors.CloudifyAgentNotImplementedError(process_management)

    @staticmethod
    def new(process_management, logger_level=logging.INFO, **params):

        """
        Creates a daemon instance that implements the required process
        management.

        :param process_management: The process management to use.
        :type process_management: str

        :param params: parameters passed to the daemon class constructor.
        :type params: dict

        :return: A daemon instance.
        :rtype `cloudify_agent.api.daemon.base.Daemon`
        """

        name = params.get('name')
        if name:
            # an explicit name was passed, make sure we don't already
            # have a daemon with that name
            try:
                DaemonFactory.load(params.get('name'))
                # this means we do have one, raise an error
                raise errors.CloudifyAgentAlreadyExistsError(name)
            except exceptions.CloudifyAgentNotFoundException:
                pass

        daemon = DaemonFactory._find_implementation(process_management)
        return daemon(logger_level=logger_level, **params)

    @classmethod
    def load(cls, name, logger_level=logging.INFO):

        """
        Loads a daemon from local storage.

        :param name: The name of the daemon to load.
        :type name: str

        :return: A daemon instance.
        :rtype `cloudify_agent.api.daemon.base.Daemon`

        :raise IOError: in case the daemon file does not exist.
        """

        storage_directory = utils.get_storage_directory()

        daemon_path = os.path.join(
            storage_directory,
            '{0}.json'.format(name)
        )
        if not os.path.exists(daemon_path):
            raise exceptions.CloudifyAgentNotFoundException(name)
        with open(daemon_path) as f:
            daemon_as_json = json.loads(f.read())
        process_management = daemon_as_json.pop('process_management')
        daemon = DaemonFactory._find_implementation(process_management)
        return daemon(logger_level=logger_level, **daemon_as_json)

    @classmethod
    def save(cls, daemon):

        """
        Saves a daemon to the local storage. The daemon is stored in json
        format and contains all daemon properties.

        :param daemon: The daemon instance to save.
        :type daemon: cloudify_agent.api.daemon.base.Daemon
        """

        storage_directory = os.path.join(utils.get_init_directory(),
                                         'daemons')

        if not os.path.exists(storage_directory):
            os.makedirs(storage_directory)

        daemon_path = os.path.join(
            storage_directory, '{0}.json'.format(
                daemon.name)
        )
        logger.debug('Saving daemon configuration')
        with open(daemon_path, 'w') as f:
            props = daemon.__dict__
            # remove non-serializable objects
            props.pop('runner')
            props.pop('logger')
            props.pop('celery')
            json.dump(props, f, indent=2)
            f.write(os.linesep)

    @classmethod
    def delete(cls, name):

        """
        Deletes a daemon from local storage.

        :param name: The name of the daemon to delete.
        :type name: str
        """

        storage_directory = utils.get_storage_directory()

        daemon_path = os.path.join(storage_directory,
                                   '{0}.json'.format(name))
        if os.path.exists(daemon_path):
            os.remove(daemon_path)
