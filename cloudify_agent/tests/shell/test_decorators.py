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

from cloudify_agent.api import exceptions
from cloudify_agent.shell.decorators import handle_failures

from cloudify_agent.tests.shell.commands import BaseCommandLineTestCase


class TestDecorators(BaseCommandLineTestCase):

    def test_api_exceptions_conversion(self):

        @click.command()
        @handle_failures
        def _raise_api_exception():
            raise exceptions.DaemonException()

        from cloudify_agent.shell.main import main
        main.add_command(_raise_api_exception, 'raise-error')
        try:
            self._run('cfy-agent raise-error', raise_system_exit=True)
            self.fail('Expected failure of command execution')
        except SystemExit as e:
            self.assertEqual(e.code, 101)

    def test_api_errors_conversion(self):

        @click.command()
        @handle_failures
        def _raise_api_error():
            raise exceptions.DaemonError()

        from cloudify_agent.shell.main import main
        main.add_command(_raise_api_error, 'raise-error')
        try:
            self._run('cfy-agent raise-error', raise_system_exit=True)
            self.fail('Expected failure of command execution')
        except SystemExit as e:
            self.assertEqual(e.code, 201)
