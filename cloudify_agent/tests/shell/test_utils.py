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

import os

from cloudify_agent.tests.shell import BaseShellTest
from cloudify_agent.shell import utils


class TestUtils(BaseShellTest):

    def test_get_init_directory(self):
        workdir = os.getcwd()
        init_directory = os.path.join(
            workdir, '.cloudify-agent'
        )
        self.assertEqual(init_directory, utils.get_init_directory())

    def test_get_storage_directory(self):
        storage_directory = os.path.join(
            utils.get_init_directory(), 'daemons'
        )
        self.assertEqual(storage_directory, utils.get_storage_directory())

    def test_failure_has_possible_solutions(self):
        failure = RuntimeError()
        failure.possible_solutions = ['dummy']
        possible_solutions = utils.get_possible_solutions(failure)
        self.assertEqual(possible_solutions, '  - dummy\n')

    def test_failure_has_no_possible_solutions(self):
        failure = RuntimeError()
        possible_solutions = utils.get_possible_solutions(failure)
        self.assertEqual(possible_solutions, '')

    def test_parse_custom_options(self):

        options = ('--key=value', '--complex-key=complex-value')
        parsed = utils.parse_custom_options(options)
        self.assertEqual(parsed,
                         {'key': 'value', 'complex_key': 'complex-value'})
