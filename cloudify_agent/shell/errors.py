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
from cloudify_agent import VIRTUALENV


class CloudifyAgentError(click.ClickException):

    """
    Base error for all errors that may be raised by the CLI.
    """

    def __init__(self, message):
        self.message = message
        super(CloudifyAgentError, self).__init__(self.__str__())

    def __str__(self):
        return '{0}{1}{2}'.format(self.message, os.linesep,
                                  utils.get_possible_solutions(self))


class CloudifyAgentNotImplementedError(CloudifyAgentError):

    """
    Error indicates no cloudify agent implementation can be
    found for the specific process management type.
    """

    def __init__(self, process_management):
        self.process_management = process_management
        super(CloudifyAgentNotImplementedError, self).__init__(self.__str__())

    def __str__(self):
        return 'No implementation found for Cloudify Agent ' \
               'of type: {0}'.format(self.process_management)


class CloudifyAgentAlreadyExistsError(CloudifyAgentError):

    """
    Error indicates that a cloudify agent with the given name already exists.
    It must be deleted before creating a new one with the same name.
    """

    def __init__(self, name):
        self.name = name
        super(CloudifyAgentAlreadyExistsError, self).__init__(self.__str__())

    def __str__(self):
        return 'Cloudify Agent {0} already exists'.format(self.name)

    @property
    def possible_solutions(self):
        return [
            "Run '{0}/bin/cloudify-agent daemon delete --name={1}' and try "
            "again".format(VIRTUALENV, self.name)
        ]
