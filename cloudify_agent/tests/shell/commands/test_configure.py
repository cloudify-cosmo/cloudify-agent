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

import mock

from cloudify_agent.shell.commands import configure

from cloudify_agent.tests.api.pm import only_ci
from cloudify_agent.tests.api.pm import only_os

from cloudify_agent.tests.shell.commands import BaseCommandLineTestCase


@mock.patch('cloudify_agent.shell.commands.configure._disable_requiretty')
@mock.patch('cloudify_agent.shell.commands.configure._fix_virtualenv')
class TestConfigureCommandLine(BaseCommandLineTestCase):

    def test_configure(self, mock_fix_virtualenv, mock_disable_requiretty):
        self._run('cfy-agent configure --disable-requiretty '
                  '--relocated-env')
        mock_disable_requiretty.assert_called_once()
        mock_fix_virtualenv.assert_called_once()

    @only_ci
    @only_os('posix')
    def test_disable_requiretty(self):
        configure._disable_requiretty()

    @only_ci
    @only_os('posix')
    def test_fix_virtualenv(self):
        configure._fix_virtualenv()
