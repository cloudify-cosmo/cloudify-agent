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

import os
import json

from cloudify.utils import setup_logger

from cloudify_agent.api import errors
from cloudify_agent.api import utils

default_logger = setup_logger('cloudify_agent.api.factory')


class DaemonFactory(object):

    """
    Factory class for manipulating various daemon instances.

    """
    def __init__(self, username=None, storage=None, logger=None):

        """
        :param username:

            the username the daemons are registered under.
            if no username if passed, the currently logged user
            will be used. this setting is used for computing
            the storage directory, hence, if `storage` is passed,
            the username will be ignored.

        :type username: str

        :param storage:

            the storage directory where daemons are stored.
            if no directory is passed, it will computed using the
            `utils.get_storage_directory` function.

        :type storage: str

        :param logger: a logger to be used to log various subsequent
                       operations.
        :type logger: logging.Logger

        """

        ######################################################################
        # `username` and `storage` are arguments because the default home
        # directory may change depending on how the daemon process is
        # executed. For example if running in a Windows Service, the home
        # directory changes. This means that we must the ability to specify
        # exactly where the storage directory is, and not let the code
        # auto-detect it in any scenario.
        #####################################################################

        self.username = username
        self.storage = storage or utils.get_storage_directory(self.username)
        self.logger = logger or default_logger

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

        daemons = []

        def _find_daemons(daemon_superclass):
            daemons.append(daemon_superclass)
            subclasses = daemon_superclass.__subclasses__()
            if subclasses:
                for subclass in subclasses:
                    _find_daemons(subclass)

        from cloudify_agent.api.pm.base import Daemon
        _find_daemons(Daemon)
        for daemon in daemons:
            if daemon.PROCESS_MANAGEMENT == process_management:
                return daemon
        raise errors.DaemonNotImplementedError(process_management)

    def new(self, logger=None, **attributes):

        """
        Creates a daemon instance that implements the required process
        management.

        :param logger: a logger to be used by the daemon to log various
                       operations.
        :type logger: logging.Logger

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
                self.load(name, logger=logger)
                # this means we do have one, raise an error
                raise errors.DaemonAlreadyExistsError(name)
            except errors.DaemonNotFoundError:
                pass

        process_management = attributes['process_management']
        daemon = DaemonFactory._find_implementation(process_management)
        return daemon(logger=logger, **attributes)

    def load_all(self, logger=None):

        """
        Loads all daemons from local storage.

        :param logger: a logger to be used by the daemons to log various
                       operations.
        :type logger: logging.Logger

        :return: all daemons instances.
        :rtype: list

        """

        if not os.path.exists(self.storage):
            return []

        daemons = []
        daemon_files = os.listdir(self.storage)
        for daemon_file in daemon_files:
            full_path = os.path.join(
                self.storage,
                daemon_file
            )
            if full_path.endswith('json'):
                self.logger.debug('Loading daemon from: {0}'.format(full_path))
                daemon_as_json = utils.json_load(full_path)
                process_management = daemon_as_json.pop('process_management')
                daemon = DaemonFactory._find_implementation(process_management)
                daemons.append(daemon(logger=logger, **daemon_as_json))
        return daemons

    def load(self, name, logger=None):

        """
        Loads a daemon from local storage.

        :param name: The name of the daemon to load.
        :type name: str

        :return: A daemon instance.
        :rtype: cloudify_agent.api.pm.base.Daemon

        :param logger: a logger to be used by the daemon to log various
                       operations.
        :type logger: logging.Logger

        :raise CloudifyAgentNotFoundException: in case the daemon
        file does not exist.
        """

        self.logger.debug('Loading daemon {0} from storage: {1}'
                          .format(name, self.storage))

        daemon_path = os.path.join(
            self.storage,
            '{0}.json'.format(name)
        )
        if not os.path.exists(daemon_path):
            raise errors.DaemonNotFoundError(name)
        daemon_as_json = utils.json_load(daemon_path)
        self.logger.debug('Daemon {0} loaded: {1}'.format(name, json.dumps(
            daemon_as_json, indent=2)))
        process_management = daemon_as_json.pop('process_management')
        daemon = DaemonFactory._find_implementation(process_management)
        return daemon(logger=logger, **daemon_as_json)

    def save(self, daemon):

        """
        Saves a daemon to the local storage. The daemon is stored in json
        format and contains all daemon properties.

        :param daemon: The daemon instance to save.
        :type daemon: cloudify_agent.api.daemon.base.Daemon

        """

        if not os.path.exists(self.storage):
            os.makedirs(self.storage)

        daemon_path = os.path.join(
            self.storage, '{0}.json'.format(
                daemon.name)
        )
        self.logger.debug('Saving daemon configuration at: {0}'
                          .format(daemon_path))
        with open(daemon_path, 'w') as f:
            props = utils.daemon_to_dict(daemon)
            json.dump(props, f, indent=2)
            f.write(os.linesep)

    def delete(self, name):

        """
        Deletes a daemon from local storage.

        :param name: The name of the daemon to delete.
        :type name: str

        """

        daemon_path = os.path.join(
            self.storage, '{0}.json'.format(name))
        if os.path.exists(daemon_path):
            os.remove(daemon_path)
