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
import getpass
from mock import patch

from cloudify_agent.api.pm.base import Daemon
from cloudify_agent.api import errors

from cloudify_agent.tests import BaseTest
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.get_storage_directory',
       get_storage_directory)
class TestDaemonDefaults(BaseTest):

    @classmethod
    def setUpClass(cls):
        cls.daemon = Daemon(
            manager_ip='manager_ip'
        )

    def test_default_basedir(self):
        self.assertEqual(os.getcwd(), self.daemon.workdir)

    def test_default_manager_port(self):
        self.assertEqual(80, self.daemon.manager_port)

    def test_default_min_workers(self):
        self.assertEqual(0, self.daemon.min_workers)

    def test_default_max_workers(self):
        self.assertEqual(5, self.daemon.max_workers)

    def test_default_broker_url(self):
        self.assertEqual('amqp://guest:guest@manager_ip:5672//',
                         self.daemon.broker_url)

    def test_default_name(self):
        self.assertTrue('cloudify-agent-' in self.daemon.name)

    def test_default_user(self):
        self.assertEqual(getpass.getuser(), self.daemon.user)

    def test_default_queue(self):
        self.assertEqual('{0}-queue'.format(
            self.daemon.name),
            self.daemon.queue)


@patch('cloudify_agent.api.utils.get_storage_directory',
       get_storage_directory)
class TestDaemonValidations(BaseTest):

    def test_missing_manager_ip(self):
        try:
            Daemon(
                name='name',
                queue='queue',
                host='queue',
                user='user'
            )
            self.fail('Expected ValueError due to missing manager_ip')
        except errors.DaemonMissingMandatoryPropertyError as e:
            self.assertTrue('manager_ip is mandatory' in e.message)

    def test_bad_min_workers(self):
        try:
            Daemon(
                name='name',
                queue='queue',
                host='queue',
                manager_ip='manager_ip',
                user='user',
                min_workers='bad'
            )
        except errors.DaemonPropertiesError as e:
            self.assertTrue('min_workers is supposed to be a number' in
                            e.message)

    def test_bad_max_workers(self):
        try:
            Daemon(
                name='name',
                queue='queue',
                host='queue',
                manager_ip='manager_ip',
                user='user',
                max_workers='bad'
            )
        except errors.DaemonPropertiesError as e:
            self.assertTrue('max_workers is supposed to be a number' in
                            e.message)

    def test_min_workers_larger_than_max_workers(self):
        try:
            Daemon(
                name='name',
                queue='queue',
                host='queue',
                manager_ip='manager_ip',
                user='user',
                max_workers=4,
                min_workers=5
            )
        except errors.DaemonPropertiesError as e:
            self.assertTrue('min_workers cannot be greater than max_workers'
                            in e.message)


@patch('cloudify_agent.api.utils.get_storage_directory',
       get_storage_directory)
class TestNotImplemented(BaseTest):

    @classmethod
    def setUpClass(cls):
        cls.daemon = Daemon(
            manager_ip='manager_ip'
        )

    def test_update_includes(self):
        self.assertRaises(NotImplementedError, self.daemon.update_includes,
                          'task')

    def start_command(self):
        self.assertRaises(NotImplementedError, self.daemon.start_command)

    def stop_command(self):
        self.assertRaises(NotImplementedError, self.daemon.stop_command)

    def test_configure(self):
        self.assertRaises(NotImplementedError, self.daemon.configure)

    def test_delete(self):
        self.assertRaises(NotImplementedError, self.daemon.delete)
