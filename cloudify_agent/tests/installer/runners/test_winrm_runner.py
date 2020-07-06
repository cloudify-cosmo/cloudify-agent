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

import pytest

from cloudify_agent.installer.runners import winrm_runner
from cloudify_agent.installer.runners.winrm_runner import split_into_chunks

from cloudify_agent.tests import BaseTest

##############################################################################
# note that this file only tests validation and defaults of the winrm runner.
# it does not test the actual functionality because that requires starting
# a vm. functional tests are executed as local workflow tests in the system
# tests framework
##############################################################################


class TestValidations(BaseTest):
    def test_validate_host(self):
        # Missing host
        session_config = {
            'user': 'test_user',
            'password': 'test_password'
        }
        with pytest.raises(ValueError, match='.*Invalid host.*'):
            winrm_runner.validate(session_config)

    def test_validate_user(self):
        # Missing user
        session_config = {
            'host': 'test_host',
            'password': 'test_password'
        }
        with pytest.raises(ValueError, match='.*Invalid user.*'):
            winrm_runner.validate(session_config)

    def test_validate_password(self):
        # Missing password
        session_config = {
            'host': 'test_host',
            'user': 'test_user'
        }
        with pytest.raises(ValueError, match='.*Invalid password.*'):
            winrm_runner.validate(session_config)


class TestDefaults(BaseTest):

    def test_defaults(self):

        runner = winrm_runner.WinRMRunner(
            validate_connection=False,
            host='test_host',
            user='test_user',
            password='test_password')

        assert runner.session_config['protocol'] == \
            winrm_runner.DEFAULT_WINRM_PROTOCOL
        assert runner.session_config['uri'] == \
            winrm_runner.DEFAULT_WINRM_URI
        assert runner.session_config['port'] == \
            winrm_runner.DEFAULT_WINRM_PORT
        assert runner.session_config['transport'] == \
            winrm_runner.DEFAULT_TRANSPORT


class TestSplitIntoChunks:
    """Test content splitting into chunks."""

    def test_empty_string(self):
        """An empty string is not splitted."""
        contents = ''
        expected_chunks = ['']
        assert split_into_chunks(contents) == expected_chunks

    def test_one_line(self):
        """A single is not splitted."""
        contents = 'this is a string'
        expected_chunks = [contents]
        assert split_into_chunks(contents) == expected_chunks

    def test_multiple_lines(self):
        """Multiple lines are splitted as expected."""
        contents = 'a\nfew\nshort\nlines'
        expected_chunks = ['a\nfew', 'short', 'lines']
        assert split_into_chunks(contents, max_size=10, separator='\n') == \
            expected_chunks

    def test_line_too_long(self):
        """Exception raised on line too long."""
        contents = 'a very long line'
        pytest.raises(ValueError, split_into_chunks, contents, max_size=1)
