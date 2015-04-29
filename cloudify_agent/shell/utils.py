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


def get_init_directory():

    """
    retrieves the inner cloudify-agent directory from the current working
    directory.

    :return: path to the initialization directory.
    :rtype `str`

    """

    workdir = os.getcwd()
    return os.path.join(
        workdir, '.cloudify-agent'
    )


def get_storage_directory():
    return os.path.join(
        get_init_directory(), 'daemons'
    )


def get_possible_solutions(failure):

    def recommend(possible_solutions):
        failure_message = 'Possible solutions'
        for solution in possible_solutions:
            failure_message = '  - {0}{1}'.format(solution, os.linesep)
        return failure_message

    if hasattr(failure, 'possible_solutions'):
        return recommend(getattr(failure, 'possible_solutions'))
    else:
        return ''


def parse_custom_options(options):

    """

    :param options: a tuple where each element is in the form of an
                       option (i.e --a=b)
    :type options: tuple

    :return: a dictionary representing the tuple.
    :rtype: dict
    """

    parsed = {}
    for option_string in options:
        parts = option_string.split('=')
        key = parts[0][2:].replace('-', '_')  # options start with '--'
        value = parts[1]
        parsed[key] = value

    return parsed