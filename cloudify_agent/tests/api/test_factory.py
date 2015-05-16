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

import uuid
from mock import patch

from cloudify_agent.api import errors as api_errors
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.tests.shell import BaseShellTest
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.get_storage_directory',
       get_storage_directory)
class TestDaemonFactory(BaseShellTest):

    def setUp(self):
        super(TestDaemonFactory, self).setUp()
        self.daemon_name = 'test-daemon-{0}'.format(uuid.uuid4())

    def test_new_initd(self):
        daemon = DaemonFactory.new(
            process_management='init.d',
            name=self.daemon_name,
            queue='queue',
            manager_ip='127.0.0.1',
            user='user',
            broker_url='127.0.0.1')
        self.assertEqual(self.daemon_name, daemon.name)
        self.assertEqual('queue', daemon.queue)
        self.assertEqual('127.0.0.1', daemon.manager_ip)
        self.assertEqual('127.0.0.1', daemon.broker_url)
        self.assertEqual('user', daemon.user)

    def test_new_wrong_plugins_attribute(self):
        self.assertRaises(ValueError, DaemonFactory.new,
                          process_management='init.d',
                          name=self.daemon_name,
                          manager_ip='127.0.0.1',
                          plugins=set(['plugin']))

    def test_new_no_implementation(self):
        self.assertRaises(api_errors.DaemonNotImplementedError,
                          DaemonFactory.new,
                          process_management='no-impl')

    def test_save_load_delete(self):

        daemon = DaemonFactory.new(
            process_management='init.d',
            name=self.daemon_name,
            queue='queue',
            manager_ip='127.0.0.1',
            user='user',
            broker_url='127.0.0.1')

        DaemonFactory.save(daemon)
        loaded = DaemonFactory.load(self.daemon_name)
        self.assertEqual('init.d', loaded.PROCESS_MANAGEMENT)
        self.assertEqual(self.daemon_name, loaded.name)
        self.assertEqual('queue', loaded.queue)
        self.assertEqual('127.0.0.1', loaded.manager_ip)
        self.assertEqual('user', loaded.user)
        self.assertEqual('127.0.0.1', daemon.broker_url)
        DaemonFactory.delete(daemon.name)
        self.assertRaises(api_errors.DaemonNotFoundError,
                          DaemonFactory.load, daemon.name)

    def test_load_non_existing(self):
        self.assertRaises(api_errors.DaemonNotFoundError,
                          DaemonFactory.load,
                          'non_existing_name')

    def test_new_existing_agent(self):

        daemon = DaemonFactory.new(
            process_management='init.d',
            name=self.daemon_name,
            queue='queue',
            manager_ip='127.0.0.1',
            user='user',
            broker_url='127.0.0.1')

        DaemonFactory.save(daemon)

        self.assertRaises(api_errors.DaemonAlreadyExistsError,
                          DaemonFactory.new,
                          process_management='init.d',
                          name=self.daemon_name,
                          queue='queue',
                          manager_ip='127.0.0.1',
                          user='user',
                          broker_url='127.0.0.1')
