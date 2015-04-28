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

import click

from cloudify_agent.shell import utils


class CloudifyAgentException(click.ClickException):

    """
    Base exception for all exceptions that may be raised by the CLI.
    """

    def __init__(self, message):
        self.message = message
        super(CloudifyAgentException, self).__init__(self.__str__())

    def __str__(self):
        return '{0}{1}{2}'.format(self.message, os.linesep,
                                  utils.get_possible_solutions(self))


class CloudifyAgentNotFoundException(CloudifyAgentException):

    """
    Exception indicating that a cloudify agent with the given name does not
    exist.
    """

    def __init__(self, name):
        self.name = name
        super(CloudifyAgentNotFoundException, self).__init__(self.__str__())

    def __str__(self):
        return 'Cloudify Agent {0} does not exist'.format(self.name)
