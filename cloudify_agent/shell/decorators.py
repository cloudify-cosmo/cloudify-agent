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

from cloudify_agent.api import exceptions as api_exceptions
from cloudify_agent.api import errors as api_errors


codes = {

    # exception start from 100
    api_exceptions.DaemonException: 101,
    api_exceptions.DaemonShutdownTimeout: 102,
    api_exceptions.DaemonStartupTimeout: 103,
    api_exceptions.DaemonStillRunningException: 104,

    # errors start from 200
    api_errors.DaemonError: 201,
    api_errors.DaemonAlreadyExistsError: 202,
    api_errors.DaemonNotFoundError: 203,
    api_errors.DaemonConfigurationError: 204,
    api_errors.DaemonMissingMandatoryPropertyError: 205,
    api_errors.DaemonNotImplementedError: 206,
    api_errors.DaemonPropertiesError: 207,
    api_errors.DaemonNotConfiguredError: 208
}


def handle_failures(func):

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except BaseException as e:
            tpe, value, tb = sys.exc_info()

            if isinstance(e, api_exceptions.DaemonException):

                # convert api exceptions to click exceptions.
                value = click.ClickException(str(e))

            if isinstance(e, api_errors.DaemonError):

                # convert api errors to cli exceptions
                value = click.ClickException(str(e))

            # set the exit_code accordingly. the exit_code property is later
            # read by the click framework to set the exit code of
            # the process.
            value.exit_code = codes.get(tpe, 1)
            raise type(value), value, tb

    return wrapper
