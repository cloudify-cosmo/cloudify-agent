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


class DaemonException(BaseException):

    """
    Base class for daemon exceptions. These exceptions indicate an error has
    occurred while executing one the daemon operations.
    """
    pass


class DaemonStartupTimeout(DaemonException):

    """
    Exception indicating that a daemon failed to start in the given timeout.
    """

    def __init__(self, timeout, name):
        self.timeout = timeout
        self.name = name
        super(DaemonStartupTimeout, self).__init__(self.__str__())

    def __str__(self):
        return 'Daemon {0} failed to start in {1} seconds' \
            .format(self.name, self.timeout)


class DaemonShutdownTimeout(DaemonException):

    """
    Exception indicating that a daemon failed to stop in the given timeout.
    """

    def __init__(self, timeout, name):
        self.timeout = timeout
        self.name = name
        super(DaemonShutdownTimeout, self).__init__(self.__str__())

    def __str__(self):
        return 'Daemon {0} failed to stop in {1} seconds'\
            .format(self.name, self.timeout)


class DaemonStillRunningException(DaemonException):

    """
    Exception indicating that a daemon process is still running.
    """

    def __init__(self, name):
        self.name = name
        super(DaemonStillRunningException, self).__init__(self.__str__())

    def __str__(self):
        return 'Daemon {0} is still running'.format(self.name)


class DaemonError(BaseException):

    """
    Base class for daemon errors. These errors are terminal and indicate a
    severe error in usage.
    """
    pass


class DaemonConfigurationError(DaemonError):

    """
    Error indicates the a faulty configuration has been passed.
    """
    pass


class DaemonPropertiesError(DaemonError):

    """
    Error indicates that faulty parameters have been passed to the daemon
    constructor.
    """
    pass


class DaemonMissingMandatoryPropertyError(DaemonPropertiesError):

    """
    Error indicating that a mandatory parameter was not supplied.
    """

    def __init__(self, param):
        self.param = param
        super(DaemonMissingMandatoryPropertyError, self).__init__(
            self.__str__())

    def __str__(self):
        return '{0} is mandatory'.format(self.param)


class DaemonNotConfiguredError(DaemonError):

    """
    Error indicating that an operation was executed that requires the
    daemon to be configured, but it isn't.
    """

    def __init__(self, name):
        self.name = name
        super(DaemonNotConfiguredError, self).__init__(self.__str__())

    def __str__(self):
        return 'Daemon {0} is not configured'.format(self.name)


class DaemonNotFoundError(DaemonError):

    """
    Error indicating that the requested daemon was not found.
    """

    def __init__(self, name):
        self.name = name
        super(DaemonNotFoundError, self).__init__(self.__str__())

    def __str__(self):
        return 'Daemon {0} not found'.format(self.name)


class DaemonAlreadyExistsError(DaemonError):

    """
    Error indicating that a request was made to create an agent with an
    already existing name.
    """

    def __init__(self, name):
        self.name = name
        super(DaemonAlreadyExistsError, self).__init__(self.__str__())

    def __str__(self):
        return 'Daemon {0} already exists'.format(self.name)


class DaemonNotImplementedError(DaemonError):

    """
    Error indicating that no implementation was found for the requested
    process management system.

    """

    def __init__(self, process_management):
        self.process_management = process_management
        super(DaemonNotImplementedError, self).__init__(self.__str__())

    def __str__(self):
        return 'No implementation found for Daemon ' \
               'of type: {0}'.format(self.process_management)


class PluginInstallationError(Exception):

    """
    Error indicating that an error occurred during a plugin
    installation process

    """
