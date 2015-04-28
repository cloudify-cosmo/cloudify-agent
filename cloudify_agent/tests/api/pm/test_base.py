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
import testtools


from cloudify_agent.api.pm.base import Daemon
from cloudify_agent.api import errors


class TestDaemonDefaults(testtools.TestCase):

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

    def test_default_host(self):
        self.assertEqual('127.0.0.1', self.daemon.host)


class TestDaemonValidations(testtools.TestCase):

    def test_missing_manager_ip(self):
        try:
            Daemon(
                name='name',
                queue='queue',
                host='queue',
                user='user'
            )
            self.fail('Expected ValueError due to missing manager_ip')
        except errors.MissingMandatoryParamError as e:
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
        except errors.DaemonParametersError as e:
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
        except errors.DaemonParametersError as e:
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
        except errors.DaemonParametersError as e:
            self.assertTrue('min_workers cannot be greater than max_workers'
                            in e.message)


class TestNotImplemented(testtools.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.daemon = Daemon(
            manager_ip='manager_ip'
        )

    def test_create(self):
        self.assertRaises(NotImplementedError, self.daemon.create)

    def test_configure(self):
        self.assertRaises(NotImplementedError, self.daemon.configure)

    def test_start(self):
        self.assertRaises(NotImplementedError, self.daemon.start, 1, 1)

    def test_register(self):
        self.assertRaises(NotImplementedError, self.daemon.register, 'dummy')

    def test_stop(self):
        self.assertRaises(NotImplementedError, self.daemon.stop, 1, 1)

    def test_delete(self):
        self.assertRaises(NotImplementedError, self.daemon.delete)

    def test_restart(self):
        self.assertRaises(NotImplementedError, self.daemon.restart, 1, 1, 1, 1)
