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

from cloudify_agent.tests.shell import BaseShellTest
from cloudify_agent.shell import utils


class TestUtils(BaseShellTest):

    def test_parse_custom_options(self):

        options = ('--key=value', '--complex-key=complex-value', '--flag')
        parsed = utils.parse_custom_options(options)
        self.assertEqual(parsed,
                         {'key': 'value',
                          'complex_key': 'complex-value',
                          'flag': True})

    def test_chdir(self):
        directory = tempfile.mkdtemp()
        original = os.getcwd()
        with utils.chdir(directory=directory):
            self.assertEqual(os.getcwd(), directory)
        self.assertEqual(os.getcwd(), original)
