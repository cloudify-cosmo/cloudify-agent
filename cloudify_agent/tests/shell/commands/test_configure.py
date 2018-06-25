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

from cloudify_agent.tests.api.pm import only_ci
from cloudify_agent.tests.api.pm import only_os

from cloudify_agent.tests.shell.commands import BaseCommandLineTestCase


class TestConfigureCommandLine(BaseCommandLineTestCase, unittest.TestCase):

    @only_ci
    @only_os('posix')
    def test_configure(self):
        self._run('cfy-agent configure --disable-requiretty '
                  '--relocated-env')
