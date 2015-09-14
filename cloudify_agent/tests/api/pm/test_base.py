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
from mock import patch

from cloudify_agent.api.pm.base import Daemon
from cloudify_agent.api import exceptions

from cloudify_agent.tests import BaseTest
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.internal.get_storage_directory',
       get_storage_directory)
class TestDaemonDefaults(BaseTest):

    def setUp(self):
        super(TestDaemonDefaults, self).setUp()
        self.daemon = Daemon(
            manager_ip='manager_ip',
            queue='queue',
            name='name',
            broker_user='guest',
            broker_pass='guest',
        )

    def test_default_workdir(self):
        self.assertEqual(self.temp_folder, self.daemon.workdir)

    def test_default_manager_port(self):
        self.assertEqual(8101, self.daemon.manager_port)

    def test_default_min_workers(self):
        self.assertEqual(0, self.daemon.min_workers)

    def test_default_max_workers(self):
        self.assertEqual(5, self.daemon.max_workers)

    def test_default_broker_url(self):
        self.assertEqual('amqp://guest:guest@manager_ip:5672//',
                         self.daemon.broker_url)

    def test_default_user(self):
        self.assertEqual(getpass.getuser(), self.daemon.user)


@patch('cloudify_agent.api.utils.internal.get_storage_directory',
       get_storage_directory)
class TestDaemonValidations(BaseTest):

    def test_missing_manager_ip(self):
        try:
            Daemon(
                name='name',
                queue='queue',
                host='queue',
                user='user',
                broker_user='guest',
                broker_pass='guest',
            )
            self.fail('Expected ValueError due to missing manager_ip')
        except exceptions.DaemonMissingMandatoryPropertyError as e:
            self.assertTrue('manager_ip is mandatory' in e.message)

    def test_bad_min_workers(self):
        try:
            Daemon(
                name='name',
                queue='queue',
                host='queue',
                manager_ip='manager_ip',
                user='user',
                min_workers='bad',
                broker_user='guest',
                broker_pass='guest',
            )
        except exceptions.DaemonPropertiesError as e:
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
                max_workers='bad',
                broker_user='guest',
                broker_pass='guest',
            )
        except exceptions.DaemonPropertiesError as e:
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
                min_workers=5,
                broker_user='guest',
                broker_pass='guest',
            )
        except exceptions.DaemonPropertiesError as e:
            self.assertTrue('min_workers cannot be greater than max_workers'
                            in e.message)


@patch('cloudify_agent.api.utils.internal.get_storage_directory',
       get_storage_directory)
class TestNotImplemented(BaseTest):

    @classmethod
    def setUpClass(cls):
        cls.daemon = Daemon(
            manager_ip='manager_ip',
            name='name',
            queue='queue',
            broker_user='guest',
            broker_pass='guest',
        )

    def test_apply_includes(self):
        self.assertRaises(NotImplementedError, self.daemon.apply_includes)

    def test_start_command(self):
        self.assertRaises(NotImplementedError, self.daemon.start_command)

    def test_stop_command(self):
        self.assertRaises(NotImplementedError, self.daemon.stop_command)

    def test_configure(self):
        self.assertRaises(NotImplementedError, self.daemon.configure)

    def test_delete(self):
        self.assertRaises(NotImplementedError, self.daemon.delete)
