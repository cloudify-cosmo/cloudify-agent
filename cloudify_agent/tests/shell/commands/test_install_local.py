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
import tempfile
import uuid
import shutil

from celery import Celery

from cloudify import ctx
from cloudify.utils import LocalCommandRunner
from cloudify.state import current_ctx
from cloudify_agent.tests import BaseTest, agent_package, agent_ssl_cert
from cloudify_agent.tests.api.pm import only_ci
from cloudify_agent.installer.config.agent_config import CloudifyAgentConfig
from cloudify_agent.installer.operations import create as create_agent
from cloudify_agent.tests.installer.config import mock_context


class TestInstaller(BaseTest):
    @classmethod
    def setUpClass(cls):
        cls._package_url = agent_package.get_package_url()

    def _test_agent_installation(self, agent_config):
        new_ctx = mock_context()
        current_ctx.set(new_ctx)

        celery = Celery()
        worker_name = 'celery@{0}'.format(agent_config['name'])
        inspect = celery.control.inspect(destination=[worker_name])

        self.assertFalse(inspect.active())
        create_agent(agent_config=agent_config)
        self.assertTrue(inspect.active())

        new_agent = ctx.instance.runtime_properties['cloudify_agent']

        agent_ssl_cert.verify_remote_cert(new_agent['agent_dir'])

        command_format = 'cfy-agent daemons {0} --name {1}'.format(
            '{0}',
            new_agent['name'])
        runner = LocalCommandRunner()
        runner.run(command_format.format('stop'))
        runner.run(command_format.format('delete'))

        self.assertFalse(inspect.active())
        return new_agent

    def _get_agent_config(self):
        return CloudifyAgentConfig({
            'name': '{0}_{1}'.format('agent_', str(uuid.uuid4())),
            'ip': 'localhost',
            'package_url': self._package_url,
            'process_management': {'name': 'init.d'},
            'rest_host': 'localhost',
            'broker_ip': 'localhost',
            'windows': os.name == 'nt',
            'local': True,
            'ssl_cert_path': self._rest_cert_path
        })

    @only_ci
    def test_installation(self):
        base_dir = tempfile.mkdtemp()
        agent_config = self._get_agent_config()
        agent_config['basedir'] = base_dir
        try:
            self._test_agent_installation(agent_config)
        finally:
            shutil.rmtree(base_dir)

    @only_ci
    def test_installation_no_basedir(self):
        agent_config = self._get_agent_config()
        new_agent = self._test_agent_installation(agent_config)
        self.assertIn('basedir', new_agent)
