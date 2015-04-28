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

    def __init__(self, timeout):
        self.timeout = timeout
        super(DaemonStartupTimeout, self).__init__(self.__str__())

    def __str__(self):
        return 'Failed to start in {0} seconds'.format(self.timeout)


class DaemonShutdownTimeout(DaemonException):

    """
    Exception indicating that a daemon failed to stop in the given timeout.
    """

    def __init__(self, timeout):
        self.timeout = timeout
        super(DaemonShutdownTimeout, self).__init__(self.__str__())

    def __str__(self):
        return 'Failed to start in {0} seconds'.format(self.timeout)


class DaemonStillRunningException(DaemonException):

    """
    Exception indicating that a daemon process is still running.
    """

    def __init__(self, name):
        self.name = name
        super(DaemonStillRunningException, self).__init__(self.__str__())

    def __str__(self):
        return 'Daemon {0} is still running'.format(self.name)
