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

import getpass
import json
import os
import tempfile
import uuid
import shutil

from celery import Celery
from mock import patch

from cloudify.utils import LocalCommandRunner
from cloudify_agent.tests import BaseTest, agent_package
from cloudify_agent.tests.api.pm import only_ci
from cloudify_agent.installer.config import configuration

from cloudify_agent.tests.installer.config import mock_context


class TestInstaller(BaseTest):

    @classmethod
    def setUpClass(cls):
        cls._package_url = agent_package.get_package_url()

    @patch('cloudify_agent.installer.config.configuration.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.attributes.ctx',
           mock_context())
    def _test_agent_installation(self, agent):
        if 'user' not in agent:
            agent['user'] = getpass.getuser()
        celery = Celery()
        worker_name = 'celery@{0}'.format(agent['name'])
        inspect = celery.control.inspect(destination=[worker_name])
        self.assertFalse(inspect.active())
        _, path = tempfile.mkstemp()
        with open(path, 'w') as agent_file:
            agent_file.write(json.dumps(agent))
        _, output_path = tempfile.mkstemp()
        runner = LocalCommandRunner()
        runner.run('cfy-agent install-local --agent-file {0} '
                   '--output-agent-file {1}'.format(path, output_path))
        self.assertTrue(inspect.active())
        with open(output_path) as new_agent_file:
            new_agent = json.loads(new_agent_file.read())
        command_format = 'cfy-agent daemons {0} --name {1}'.format(
            '{0}',
            new_agent['name'])
        runner.run(command_format.format('stop'))
        runner.run(command_format.format('delete'))
        self.assertFalse(inspect.active())
        return new_agent

    @patch('cloudify_agent.installer.config.configuration.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.attributes.ctx',
           mock_context())
    def _prepare_configuration(self, agent):
        agent['name'] = '{0}_{1}'.format(
            agent.get('name', 'agent_'),
            str(uuid.uuid4()))
        configuration.reinstallation_attributes(agent)

    @only_ci
    def test_installation(self):
        base_dir = tempfile.mkdtemp()
        agent = {
            'ip': 'localhost',
            'package_url': self._package_url,
            'manager_ip': 'localhost',
            'basedir': base_dir,
            'windows': os.name == 'nt',
            'local': False,
            'broker_get_settings_from_manager': False
        }
        try:
            self._prepare_configuration(agent)
            self._test_agent_installation(agent)
        finally:
            shutil.rmtree(base_dir)

    @only_ci
    def test_installation_no_basedir(self):
        agent = {
            'ip': 'localhost',
            'package_url': self._package_url,
            'manager_ip': 'localhost',
            'windows': os.name == 'nt',
            'local': False,
            'broker_get_settings_from_manager': False
        }
        self._prepare_configuration(agent)
        self.assertNotIn('basedir', agent)
        new_agent = self._test_agent_installation(agent)
        self.assertIn('basedir', new_agent)
