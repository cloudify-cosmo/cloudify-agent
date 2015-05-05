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

import mock

from cloudify_agent.tests.shell.commands import BaseCommandLineTestCase


@mock.patch('cloudify_agent.shell.commands.configure.api_utils')
class TestConfigureCommandLine(BaseCommandLineTestCase):

    def test_configure(self, mock_api_utils):
        self._run('cfy agent configure --disable-requiretty '
                  '--relocated-env')
        mock_api_utils.disable_requiretty.assert_called_once()
        mock_api_utils.fix_virtualenv.assert_called_once()
