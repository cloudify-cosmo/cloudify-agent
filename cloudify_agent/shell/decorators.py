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

import click
import sys
from functools import wraps

from cloudify_agent.api import exceptions


codes = {

    # exception start from 100
    exceptions.DaemonException: 101,
    exceptions.DaemonShutdownTimeout: 102,
    exceptions.DaemonStartupTimeout: 103,
    exceptions.DaemonStillRunningException: 104,

    # errors start from 200
    exceptions.DaemonError: 201,
    exceptions.DaemonAlreadyExistsError: 202,
    exceptions.DaemonNotFoundError: 203,
    exceptions.DaemonConfigurationError: 204,
    exceptions.DaemonMissingMandatoryPropertyError: 205,
    exceptions.DaemonNotImplementedError: 206,
    exceptions.DaemonPropertiesError: 207,
    exceptions.DaemonNotConfiguredError: 208,
    exceptions.PluginInstallationError: 209
}


def handle_failures(func):

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except BaseException as e:
            tpe, value, tb = sys.exc_info()

            if isinstance(e, exceptions.DaemonException):

                # convert api exceptions to click exceptions.
                value = click.ClickException(str(e))

            if isinstance(e, exceptions.DaemonError):

                # convert api errors to cli exceptions
                value = click.ClickException(str(e))

            # set the exit_code accordingly. the exit_code property is later
            # read by the click framework to set the exit code of
            # the process.
            value.exit_code = codes.get(tpe, 1)
            raise type(value), value, tb

    return wrapper
