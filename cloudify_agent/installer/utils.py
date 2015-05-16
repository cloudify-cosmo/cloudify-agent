#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
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

import tempfile
import os
import copy


def env_to_file(env_variables, destination_path=None):

    """
    Write environment variables to a file.

    :param env_variables: environment variables
    :type env_variables: dict

    :param destination_path: destination path of a file where the
    environment variables will be stored. the stored variables will be a
    bash script you can then source.
    :type destination_path: str

    :return: path to the file containing the env variables
    :rtype `str`
    """

    if not destination_path:
        destination_path = tempfile.mkstemp(suffix='env')[1]

    with open(destination_path, 'w') as f:
        f.write('#!/bin/bash')
        f.write(os.linesep)
        f.write(os.linesep)
        for key, value in env_variables.iteritems():
            f.write('export {0}={1}'.format(key, value))
            f.write(os.linesep)
        f.write(os.linesep)

    return destination_path


def stringify_values(dictionary):

    """
    Given a dictionary convert all values into the string representation of
    the value. useful for dicts that only allow string values (like os.environ)

    :param dictionary: the dictionary to convert
    :return: a copy of the dictionary where all values are now string.
    :rtype: dict
    """

    dict_copy = copy.deepcopy(dictionary)

    for key, value in dict_copy.iteritems():
        if isinstance(value, dict):
            dict_copy[key] = stringify_values(value)
        else:
            dict_copy[key] = str(value)
    return dict_copy


def purge_none_values(dictionary):

    """
    Given a dictionary remove all key who's value is None.

    :param dictionary: the dictionary to convert
    :return: a copy of the dictionary where no key has a None value
    :rtype: dict
    """

    dict_copy = copy.deepcopy(dictionary)
    for key, value in dictionary.iteritems():
        if dictionary[key] is None:
            del dict_copy[key]
    return dict_copy
