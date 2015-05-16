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

import sys

from cloudify_agent.shell import main as cli
from cloudify_agent.tests.shell import BaseShellTest


class BaseCommandLineTestCase(BaseShellTest):

    def _run(self, command, raise_system_exit=False):
        sys.argv = command.split()
        self.logger.info('Running cfy-agent command with sys.argv={'
                         '0}'.format(sys.argv))
        try:
            cli.main()
        except SystemExit as e:
            if raise_system_exit and e.code != 0:
                raise
