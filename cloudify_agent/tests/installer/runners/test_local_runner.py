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

import os
import tempfile
import logging
import platform

from cloudify.utils import setup_logger

from cloudify_agent.installer.runners.local_runner import LocalRunner
from cloudify_agent.tests.file_server import FileServer
from cloudify_agent.tests.file_server import PORT
from cloudify_agent.tests import BaseTest
from cloudify_agent import tests


class LocalRunnerTest(BaseTest):

    fs = None
    runner = None

    @classmethod
    def setUpClass(cls):
        super(LocalRunnerTest, cls).setUpClass()
        cls.logger = setup_logger(cls.__name__)
        cls.logger.setLevel(logging.DEBUG)
        cls.runner = LocalRunner(
            logger=cls.logger)
        resources = os.path.join(
            os.path.dirname(tests.__file__),
            'resources'
        )
        cls.fs = FileServer(resources)
        cls.fs.start()

    @classmethod
    def tearDownClass(cls):
        super(LocalRunnerTest, cls).tearDownClass()
        cls.fs.stop()

    def test_run_command(self):
        response = self.runner.run('echo hello')
        self.assertIn('hello', response.output)

    def test_run_command_with_env(self):
        response = self.runner.run('env',
                                   execution_env={'TEST_KEY': 'TEST_VALUE'})
        self.assertIn('TEST_KEY=TEST_VALUE', response.output)

    def test_download(self):
        output_path = self.runner.download(
            url='http://localhost:{0}/archive.tar.gz'.format(PORT))
        self.logger.info('Downloaded archive to path: {0}'.format(output_path))
        self.assertTrue(os.path.exists(output_path))

    def test_extract(self):
        temp_folder = tempfile.mkdtemp()
        output_path = self.runner.download(
            url='http://localhost:{0}/archive.tar.gz'.format(PORT))
        self.runner.extract(archive=output_path, destination=temp_folder)
        self.assertTrue(os.path.exists(
            os.path.join(temp_folder, 'dsl_parser'))
        )

    def test_validate_connection(self):
        self.runner.validate_connection()

    def test_machine_distribution(self):
        dist = self.runner.machine_distribution()
        expected_dist = platform.dist()
        self.assertEqual(expected_dist[0], dist[0])
        self.assertEqual(expected_dist[1], dist[1])
        self.assertEqual(expected_dist[2], dist[2])
