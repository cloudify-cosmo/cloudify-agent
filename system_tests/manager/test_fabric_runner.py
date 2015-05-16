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

from cloudify.workflows import local
from cloudify.utils import setup_logger
from cosmo_tester.framework import testenv
from worker_installer.runners.fabric_runner import FabricRunner
from system_tests import resources


class RemoteFabricRunnerTest(testenv.TestCase):

    runner = None

    @classmethod
    def setUpClass(cls):
        super(RemoteFabricRunnerTest, cls).setUpClass()
        cls.logger = setup_logger(cls.__name__)
        cls.logger.setLevel(logging.DEBUG)
        cls.runner = FabricRunner(
            logger=cls.logger,
            validate_connection=False)

    def setUp(self):

        self.addCleanup(self.cleanup)

        blueprint_path = resources.get_resource(
            'fabric-runner-machine-blueprint/'
            'fabric-runner-machine-blueprint.yaml')
        self.logger.info('Initiating local env')

        inputs = {
            'prefix': self._testMethodName,
            'external_network': self.env.external_network_name,
            'os_username': self.env.keystone_username,
            'os_password': self.env.keystone_password,
            'os_tenant_name': self.env.keystone_tenant_name,
            'os_region': self.env.region,
            'os_auth_url': self.env.keystone_url,
            'image_id': self.env.ubuntu_trusty_image_id,
            'flavor': self.env.medium_flavor_id,
            'key_pair_path': '{0}/{1}-keypair.pem'
            .format(self.workdir, self._testMethodName)
        }

        self.local_env = local.init_env(
            blueprint_path=blueprint_path,
            ignored_modules='plugin_installer.tasks',
            inputs=inputs)

        self.local_env.execute('install', task_retries=0)

    def cleanup(self):
        self.local_env.execute(
            'uninstall',
            task_retries=5,
            task_retry_interval=10)

    def test_runner(self):

        ##################################################################
        # the reason these tests are not separated is because we need to
        # provision a VM for the to run. and we only want to do it once,
        # this can be done in the setupClass method, but currently using
        # self.env is not supported in the setupClass method,
        # which is needed for the local workflow inputs.
        ##################################################################

        self._test_download()
        self._test_exists()
        self._test_get_non_existing_file()
        self._test_machine_distribution()
        self._test_ping()
        self._test_put_get_file()
        self._test_run_command()
        self._test_run_command_with_env()
        self._test_run_script()
        self._test_extract()

    def _test_ping(self):
        self.runner.ping()

    def _test_run_command(self):
        response = self.runner.run('echo hello')
        self.assertIn('hello', response.output)

    def _test_run_script(self):

        script = tempfile.mktemp()
        self.logger.info('Created temporary file for script: {0}'
                         .format(script))

        with open(script, 'w') as f:
            f.write('#!/bin/bash')
            f.write(os.linesep)
            f.write('echo hello')
            f.write(os.linesep)

        response = self.runner.run_script(script=script)
        self.assertEqual('hello', response.output.rstrip())

    def _test_exists(self):
        response = self.runner.exists(tempfile.gettempdir())
        self.assertTrue(response)

    def _test_get_non_existing_file(self):
        try:
            self.runner.get_file(src='non-exiting')
        except IOError:
            pass

    def _test_put_get_file(self):

        src = tempfile.mktemp()

        with open(src, 'w') as f:
            f.write('test_put_get_file')

        remote_path = self.runner.put_file(src=src)
        local_path = self.runner.get_file(src=remote_path)

        with open(local_path) as f:
            self.assertEqual('test_put_get_file',
                             f.read())

    def _test_run_command_with_env(self):
        response = self.runner.run('env',
                                   execution_env={'TEST_KEY': 'TEST_VALUE'})
        self.assertIn('TEST_KEY=TEST_VALUE', response.output)

    def _test_download(self):
        output_path = self.runner.download(
            url='http://google.com')
        self.logger.info('Downloaded index to path: {0}'.format(output_path))
        self.assertTrue(self.runner.exists(path=output_path))

    def _test_extract(self):
        temp_folder = self.runner.mkdtemp()
        output_path = self.runner.download(
            url='https://github.com/cloudify-cosmo/'
                'cloudify-agent-installer-plugin/archive/master.tar.gz')
        self.runner.extract(archive=output_path, destination=temp_folder)
        self.assertTrue(self.runner.exists(
            os.path.join(temp_folder, 'worker_installer'))
        )

    def _test_machine_distribution(self):
        dist = self.runner.machine_distribution()
        self.assertEqual('Ubuntu', dist[0])
        self.assertEqual('14.04', dist[1])
        self.assertEqual('trusty', dist[2])
