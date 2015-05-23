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
    def new(logger_level=logging.INFO, logger_format=None,
            username=None, storage=None, **attributes):

        """
        Creates a daemon instance that implements the required process
        management.

        :param logger_level: the daemon logger level. Note that this is not
        the log level of the daemon itself, but rather the log level for
        the logger creating and configuring the daemon
        :type logger_level: int

        :param logger_format: the daemon logger format. Note that this is not
        the log format of the daemon itself, but rather the log format for
        the logger creating and configuring the daemon.
        :type logger_format: str

        :param username:

            the username the daemon is registered under.
            if no username if passed, the currently logged user
            will be used. this setting is used for computing
            the storage directory, hence, if `storage` is passed,
            the username will be ignored.

        :type username: str
        :param storage: the storage directory
        :type storage: str

        :param attributes: parameters passed to the daemon class constructor.
        :type attributes: dict

        :return: A daemon instance.
        :rtype: cloudify_agent.api.pm.base.Daemon
        """

        name = attributes.get('name')
        if name:
            # an explicit name was passed, make sure we don't already
            # have a daemon with that name
            try:
                DaemonFactory.load(name, username=username, storage=storage)
                # this means we do have one, raise an error
                raise errors.DaemonAlreadyExistsError(name)
            except errors.DaemonNotFoundError:
                pass

        process_management = attributes['process_management']
        daemon = DaemonFactory._find_implementation(process_management)
        return daemon(logger_level=logger_level,
                      logger_format=logger_format, **attributes)

    @staticmethod
    def load_all(username=None, storage=None):

        """
        Loads all daemons from local storage.

        :param username:

            the username the daemon is registered under.
            if no username if passed, the currently logged user
            will be used. this setting is used for computing
            the storage directory, hence, if `storage` is passed,
            the username will be ignored.

        :type username: str
        :param storage: the storage directory
        :type storage: str

        :return: all daemons instances.
        :rtype: list

        """

        if storage is None:
            storage = utils.get_storage_directory(username)

        if not os.path.exists(storage):
            return []

        daemons = []
        daemon_files = os.listdir(storage)
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

    @staticmethod
    def load(name, logger_level=None, logger_format=None,
             username=None, storage=None):

        """
        Loads a daemon from local storage.

        :param name: The name of the daemon to load.
        :type name: str
        :param logger_level:

            The level of the logger of the loaded daemon.
            if not specified, the value given at first
            instantiation will be used.
        :type logger_level: int

        :param logger_format:

            The format of the logger of the loaded daemon.
            if not specified, the value given at first
            instantiation will be used.
        :type logger_format: int
        :param username:

            the username the daemon is registered under.
            if no username if passed, the currently logged user
            will be used. this setting is used for computing
            the storage directory, hence, if `storage` is passed,
            the username will be ignored.

        :type username: str
        :param storage: the storage directory
        :type storage: str

        :return: A daemon instance.
        :rtype: cloudify_agent.api.pm.base.Daemon

        :raise CloudifyAgentNotFoundException: in case the daemon
        file does not exist.
        """

        if storage is None:
            storage = utils.get_storage_directory(username)

        logger.info('Loading daemon {0} from storage: {1}'
                    .format(name, storage))

        daemon_path = os.path.join(
            storage,
            '{0}.json'.format(name)
        )
        if not os.path.exists(daemon_path):
            raise errors.DaemonNotFoundError(name)
        daemon_as_json = utils.json_load(daemon_path)
        if logger_level:
            daemon_as_json['logger_level'] = logger_level
        if logger_format:
            daemon_as_json['logger_format'] = logger_format
        logger.debug('Daemon {0} loaded: {1}'.format(name, json.dumps(
            daemon_as_json, indent=2)))
        process_management = daemon_as_json.pop('process_management')
        daemon = DaemonFactory._find_implementation(process_management)
        return daemon(**daemon_as_json)

    @staticmethod
    def save(daemon, username=None, storage=None):

        """
        Saves a daemon to the local storage. The daemon is stored in json
        format and contains all daemon properties.

        :param daemon: The daemon instance to save.
        :type daemon: cloudify_agent.api.daemon.base.Daemon

        :param username:

            the username the daemon is registered under.
            if no username if passed, the currently logged user
            will be used. this setting is used for computing
            the storage directory, hence, if `storage` is passed,
            the username will be ignored.

        :type username: str
        :param storage: the storage directory
        :type storage: str

        """

        if storage is None:
            storage = utils.get_storage_directory(username)

        if not os.path.exists(storage):
            os.makedirs(storage)

        daemon_path = os.path.join(
            storage, '{0}.json'.format(
                daemon.name)
        )
        logger.debug('Saving daemon configuration at: {0}'
                     .format(daemon_path))
        with open(daemon_path, 'w') as f:
            props = utils.daemon_to_dict(daemon)
            json.dump(props, f, indent=2)
            f.write(os.linesep)

    @staticmethod
    def delete(name, username=None, storage=None):

        """
        Deletes a daemon from local storage.

        :param name: The name of the daemon to delete.
        :type name: str
        :param username:

            the username the daemon is registered under.
            if no username if passed, the currently logged user
            will be used. this setting is used for computing
            the storage directory, hence, if `storage` is passed,
            the username will be ignored.

        :type username: str
        :param storage: the storage directory
        :type storage: str

        """

        if storage is None:
            storage = utils.get_storage_directory(username)

        daemon_path = os.path.join(
            storage, '{0}.json'.format(name))
        if os.path.exists(daemon_path):
            os.remove(daemon_path)
