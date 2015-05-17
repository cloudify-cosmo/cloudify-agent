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

import logging
import tempfile
import os

from cloudify.utils import setup_logger

from cloudify_agent.tests import BaseTest


class BaseShellTest(BaseTest):

    def setUp(self):
        super(BaseShellTest, self).setUp()
        self.logger = setup_logger(
            'cloudify-agent.tests.shell',
            logger_level=logging.DEBUG)
        self.currdir = os.getcwd()
        self.workdir = tempfile.mkdtemp(
            prefix='cfy-agent-shell-tests-')
        self.logger.info('Working directory: {0}'.format(self.workdir))
        os.chdir(self.workdir)

    def tearDown(self):
        super(BaseShellTest, self).tearDown()
        os.chdir(self.currdir)
