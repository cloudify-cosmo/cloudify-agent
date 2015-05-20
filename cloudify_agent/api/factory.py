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

from cloudify_agent.api import errors
from cloudify_agent.api import utils

logger = setup_logger('cloudify_agent.api.factory')


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

        from cloudify_agent.api.pm.base import Daemon
        daemons = Daemon.__subclasses__()
        for daemon in daemons:
            if daemon.PROCESS_MANAGEMENT == process_management:
                return daemon
        raise errors.DaemonNotImplementedError(process_management)

    @staticmethod
    def new(process_management, logger_level=logging.INFO, **attributes):

        """
        Creates a daemon instance that implements the required process
        management.

        :param process_management: The process management to use.
        :type process_management: str

        :param params: parameters passed to the daemon class constructor.
        :type params: dict

        :return: A daemon instance.
        :rtype: cloudify_agent.api.pm.base.Daemon
        """

        name = attributes.get('name')
        if name:
            # an explicit name was passed, make sure we don't already
            # have a daemon with that name
            try:
                DaemonFactory.load(name)
                # this means we do have one, raise an error
                raise errors.DaemonAlreadyExistsError(name)
            except errors.DaemonNotFoundError:
                pass

        daemon = DaemonFactory._find_implementation(process_management)
        return daemon(logger_level=logger_level,
                      logger_format='%(message)s', **attributes)

    @staticmethod
    def load_all():

        if not os.path.exists(utils.get_storage_directory()):
            return []

        daemons = []
        daemon_files = os.listdir(utils.get_storage_directory())
        for daemon_file in daemon_files:
            full_path = os.path.join(
                utils.get_storage_directory(),
                daemon_file
            )
            if full_path.endswith('json'):
                logger.debug('Loading daemon from: {0}'.format(full_path))
                daemon_as_json = utils.json_load(full_path)
                process_management = daemon_as_json.pop('process_management')
                daemon = DaemonFactory._find_implementation(process_management)
                daemons.append(daemon(**daemon_as_json))
        return daemons

    @classmethod
    def load(cls, name):

        """
        Loads a daemon from local storage.

        :param name: The name of the daemon to load.
        :type name: str

        :return: A daemon instance.
        :rtype: cloudify_agent.api.pm.base.Daemon

        :raise CloudifyAgentNotFoundException: in case the daemon
        file does not exist.
        """

        storage_directory = utils.get_storage_directory()

        daemon_path = os.path.join(
            storage_directory,
            '{0}.json'.format(name)
        )
        if not os.path.exists(daemon_path):
            raise errors.DaemonNotFoundError(name)
        logger.debug('Loading daemon {0} from storage: {1}'
                     .format(name, storage_directory))
        daemon_as_json = utils.json_load(daemon_path)
        logger.debug('Daemon {0} loaded: {1}'.format(name, json.dumps(
            daemon_as_json, indent=2)))
        process_management = daemon_as_json.pop('process_management')
        daemon = DaemonFactory._find_implementation(process_management)
        return daemon(**daemon_as_json)

    @classmethod
    def save(cls, daemon):

        """
        Saves a daemon to the local storage. The daemon is stored in json
        format and contains all daemon properties.

        :param daemon: The daemon instance to save.
        :type daemon: cloudify_agent.api.daemon.base.Daemon
        """

        storage_directory = os.path.join(utils.get_storage_directory())

        if not os.path.exists(storage_directory):
            os.makedirs(storage_directory)

        daemon_path = os.path.join(
            storage_directory, '{0}.json'.format(
                daemon.name)
        )
        logger.debug('Saving daemon configuration at: {0}'
                     .format(daemon_path))
        with open(daemon_path, 'w') as f:
            props = utils.daemon_to_dict(daemon)
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

        daemon_path = os.path.join(
            storage_directory, '{0}.json'.format(name))
        if os.path.exists(daemon_path):
            os.remove(daemon_path)
