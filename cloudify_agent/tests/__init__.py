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

import os
import logging
import tempfile
import getpass
import shutil

import unittest2 as unittest

from cloudify.utils import setup_logger


try:
    win_error = WindowsError
except NameError:
    win_error = None


def get_storage_directory(_=None):
    return os.path.join(tempfile.gettempdir(), 'cfy-agent-tests-daemons')


class BaseTest(unittest.TestCase):

    def setUp(self):

        # change levels to 'DEBUG' to troubleshoot.
        self.logger = setup_logger(
            'cloudify-agent.tests',
            logger_level=logging.INFO)
        from cloudify_agent.api import utils
        utils.logger.setLevel(logging.INFO)

        self.curr_dir = os.getcwd()
        self.temp_folder = tempfile.mkdtemp(prefix='cfy-agent-tests-')

        def clean_temp_folder():
            try:
                shutil.rmtree(self.temp_folder)
            except win_error:
                # no hard feeling if file is locked.
                pass
        self.addCleanup(clean_temp_folder)
        os.chdir(self.temp_folder)
        self.addCleanup(lambda: os.chdir(self.curr_dir))

        self.username = getpass.getuser()
        self.logger.info('Working directory: {0}'.format(self.temp_folder))
