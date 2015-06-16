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

import uuid
import os
import shutil

from cloudify_agent.api import errors as api_errors
from cloudify_agent.api import utils
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.tests.shell import BaseShellTest
from cloudify_agent.tests import get_storage_directory


class TestDaemonFactory(BaseShellTest):

    def setUp(self):
        super(TestDaemonFactory, self).setUp()
        self.daemon_name = 'test-daemon-{0}'.format(uuid.uuid4())
        self.factory = DaemonFactory(storage=get_storage_directory())

    def test_new_initd(self):
        daemon = self.factory.new(
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

    def test_new_wrong_includes_attribute(self):
        self.assertRaises(ValueError, self.factory.new,
                          process_management='init.d',
                          queue='{0}-queue'.format(self.daemon_name),
                          name=self.daemon_name,
                          manager_ip='127.0.0.1',
                          includes=set(['plugin']))

    def test_new_no_implementation(self):
        self.assertRaises(api_errors.DaemonNotImplementedError,
                          self.factory.new,
                          process_management='no-impl')

    def test_save_load_delete(self):

        daemon = self.factory.new(
            process_management='init.d',
            name=self.daemon_name,
            queue='queue',
            manager_ip='127.0.0.1',
            user='user',
            broker_url='127.0.0.1')

        self.factory.save(daemon)
        loaded = self.factory.load(self.daemon_name)
        self.assertEqual('init.d', loaded.PROCESS_MANAGEMENT)
        self.assertEqual(self.daemon_name, loaded.name)
        self.assertEqual('queue', loaded.queue)
        self.assertEqual('127.0.0.1', loaded.manager_ip)
        self.assertEqual('user', loaded.user)
        self.assertEqual('127.0.0.1', daemon.broker_url)
        self.factory.delete(daemon.name)
        self.assertRaises(api_errors.DaemonNotFoundError,
                          self.factory.load, daemon.name)

    def test_load_non_existing(self):
        self.assertRaises(api_errors.DaemonNotFoundError,
                          self.factory.load,
                          'non_existing_name')

    def test_load_all(self):

        def _save_daemon(name):
            daemon = self.factory.new(
                process_management='init.d',
                name=name,
                queue='queue',
                manager_ip='127.0.0.1',
                user='user',
                broker_url='127.0.0.1')
            self.factory.save(daemon)

        if os.path.exists(get_storage_directory()):
            shutil.rmtree(get_storage_directory())

        daemons = self.factory.load_all()
        self.assertEquals(0, len(daemons))

        _save_daemon(utils.internal.generate_agent_name())
        _save_daemon(utils.internal.generate_agent_name())
        _save_daemon(utils.internal.generate_agent_name())

        daemons = self.factory.load_all()
        self.assertEquals(3, len(daemons))

    def test_new_existing_agent(self):

        daemon = self.factory.new(
            process_management='init.d',
            name=self.daemon_name,
            queue='queue',
            manager_ip='127.0.0.1',
            user='user',
            broker_url='127.0.0.1')

        self.factory.save(daemon)

        self.assertRaises(api_errors.DaemonAlreadyExistsError,
                          self.factory.new,
                          process_management='init.d',
                          name=self.daemon_name,
                          queue='queue',
                          manager_ip='127.0.0.1',
                          user='user',
                          broker_url='127.0.0.1')
