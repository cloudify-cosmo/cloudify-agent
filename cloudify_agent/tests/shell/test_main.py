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
import unittest

import mock
import json
import logging
import pkgutil

import click

from cloudify_agent.tests.shell.commands import BaseCommandLineTestCase


class TestCommandLine(BaseCommandLineTestCase, unittest.TestCase):

    def test_debug_command_line(self):

        @click.command()
        def log():
            pass

        from cloudify_agent.shell.main import main
        main.add_command(log, 'log')
        self._run('cfy-agent --debug log')

        # assert all loggers are now at debug level
        from cloudify_agent.api.utils import logger
        self.assertEqual(logger.level, logging.DEBUG)

    def test_version(self):
        mock_logger = mock.Mock()
        with mock.patch('cloudify_agent.shell.main.get_logger',
                        return_value=mock_logger):
            self._run('cfy-agent --version')
        self.assertEqual(1, len(mock_logger.mock_calls))
        version = json.loads(
            pkgutil.get_data('cloudify_agent', 'VERSION'))['version']
        log_args = mock_logger.mock_calls[0][1]
        logged_output = log_args[0]
        self.assertIn(version, logged_output)
