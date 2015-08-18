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
import tempfile
import uuid

from celery import Celery
from mock import patch

from cloudify.utils import LocalCommandRunner
from cloudify_agent.tests import BaseTest
from cloudify_agent.installer.config import configuration

from cloudify_agent.tests.installer.config import mock_context


PACKAGE_URL = ('http://gigaspaces-repository-eu.s3.amazonaws.com/org/'
               'cloudify3/3.3.0/m3-RELEASE/'
               'cloudify-ubuntu-trusty-agent_3.3.0-m3-b273.tar.gz')


class TestInstaller(BaseTest):

    @patch('cloudify_agent.installer.config.configuration.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.decorators.ctx',
           mock_context())
    @patch('cloudify_agent.installer.config.attributes.ctx',
           mock_context())
    def test_installation(self):
        user = getpass.getuser()
        name = str(uuid.uuid4())
        base_dir = tempfile.mkdtemp()
        agent = {
            "ip": "localhost",
            "fabric_env": {},
            "package_url": PACKAGE_URL,
            "process_management": {
                "name": "init.d"
            },
            "manager_ip": "localhost",
            "distro_codename": "trusty",
            "basedir": base_dir,
            "port": 22,
            "env": {},
            "system_python": "python",
            "min_workers": 0,
            "distro": "ubuntu",
            "max_workers": 5,
            "user": user,
            "broker_url": "amqp://guest:guest@127.0.0.1:5672//",
            "name": name,
            "windows": False,
            "local": False,
            "disable_requiretty": True
        }
        configuration.reinstallation_attributes(agent)
        celery = Celery()
        worker_name = 'celery@{0}'.format(agent['name'])
        inspect = celery.control.inspect(destination=[worker_name])
        self.assertFalse(inspect.active())
        _, path = tempfile.mkstemp()
        with open(path, 'w') as agent_file:
            agent_file.write(json.dumps(agent))
        runner = LocalCommandRunner()
        runner.run('cfy-agent install_local --agent-file {0}'.format(path))
        self.assertTrue(inspect.active())
        cfy_agent_path = '{0}/bin/cfy-agent'.format(agent['envdir'])
        command_format = '{0} daemons {1} --name {2}'.format(
            cfy_agent_path,
            '{0}',
            name)
        runner.run(command_format.format('stop'), cwd=base_dir)
        runner.run(command_format.format('delete'), cwd=base_dir)
        self.assertFalse(inspect.active())
