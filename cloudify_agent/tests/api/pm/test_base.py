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

from copy import copy
import getpass
from mock import patch
import os

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
        )

    def test_default_workdir(self):
        self.assertEqual(self.temp_folder, self.daemon.workdir)

    def test_default_manager_port(self):
        self.assertEqual(8101, self.daemon.manager_port)

    def test_default_min_workers(self):
        self.assertEqual(0, self.daemon.min_workers)

    def test_default_max_workers(self):
        self.assertEqual(5, self.daemon.max_workers)

    def test_default_broker_user(self):
        self.assertEqual('guest',
                         self.daemon.broker_user)

    def test_default_broker_pass(self):
        self.assertEqual('guest',
                         self.daemon.broker_pass)

    def test_default_broker_port(self):
        self.assertEqual(5672,
                         self.daemon.broker_port)

    def test_default_broker_url(self):
        self.assertEqual('amqp://guest:guest@manager_ip:5672//',
                         self.daemon.broker_url)

    def test_default_broker_ssl(self):
        self.assertEqual(False,
                         self.daemon.broker_ssl_enabled)

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


class TestDeleteAMQPQueues(BaseTest):
    """
        This is a private method, but it has proven fragile in implementing
        the broker security changes.
    """

    # This MUST NOT include broker_user or broker_pass
    default_daemon_args = {
        'manager_ip': 'manager_ip',
        'name': 'name',
        'queue': 'queue',
    }

    @patch('cloudify_agent.api.pm.base.amqp_client')
    def test_delete_queues_default_credentials(self, mock_amqp_client):
        daemon = Daemon(**self.default_daemon_args)

        daemon._delete_amqp_queues()

        mock_amqp_client.create_client.assert_called_once_with(
            amqp_host='manager_ip',
            amqp_user='guest',
            amqp_pass='guest',
            ssl_enabled=False,
            ssl_cert_path='',
        )

    @patch('cloudify_agent.api.pm.base.amqp_client')
    def test_delete_queues_provided_credentials(self, mock_amqp_client):
        broker_user = 'testuser'
        broker_pass = 'cloudifytesting'

        daemon_args = copy(self.default_daemon_args)
        daemon_args.update({
            'broker_user': broker_user,
            'broker_pass': broker_pass,
        })

        daemon = Daemon(**daemon_args)

        daemon._delete_amqp_queues()

        mock_amqp_client.create_client.assert_called_once_with(
            amqp_host='manager_ip',
            amqp_user=broker_user,
            amqp_pass=broker_pass,
            ssl_enabled=False,
            ssl_cert_path='',
        )

    @patch('cloudify_agent.api.pm.base.os.makedirs')
    @patch('cloudify_agent.api.pm.base.amqp_client')
    def test_delete_queues_with_ssl(self, mock_amqp_client, mock_os):
        cert_dir = '/not/a/real'
        cert_path = os.path.join('/not/a/real', 'broker.crt')

        daemon_args = copy(self.default_daemon_args)
        daemon_args.update({
            'broker_ssl_enabled': True,
            'workdir': cert_dir,
            # This will need to be a valid-ish cert when we start validating
            'broker_ssl_cert': 'notarealcert',
        })

        daemon = Daemon(**daemon_args)

        daemon._delete_amqp_queues()

        mock_amqp_client.create_client.assert_called_once_with(
            amqp_host='manager_ip',
            amqp_user='guest',
            amqp_pass='guest',
            ssl_enabled=True,
            ssl_cert_path=cert_path,
        )


class TestBrokerUrl(BaseTest):

    # This MUST NOT include broker_user or broker_pass
    default_daemon_args = {
        'manager_ip': 'manager_ip',
        'name': 'name',
        'queue': 'queue',
    }

    # Default arguments for this are handled in the defaults test case above

    def test_broker_url_cannot_be_set(self):
        # If broker URL can be set then extra handling will be required to
        # determine what the components are to use with amqp_client, and to
        # decide whether to use supplied user/pass/etc if they differ from
        # those in the URL.
        # As the part that causes the problem of needing to determine the
        # components is the amqp_client, the test is here.
        daemon_args = copy(self.default_daemon_args)
        daemon_args.update({
            'broker_url': 'thisshouldbeignored',
        })

        daemon = Daemon(**daemon_args)

        self.assertEqual('amqp://guest:guest@manager_ip:5672//',
                         daemon.broker_url)

    def test_broker_url_provided_credentials(self):
        broker_user = 'testuser'
        broker_pass = 'cloudifytesting'

        daemon_args = copy(self.default_daemon_args)
        daemon_args.update({
            'broker_user': broker_user,
            'broker_pass': broker_pass,
        })

        daemon = Daemon(**daemon_args)

        self.assertEqual(
            'amqp://{user}:{password}@manager_ip:5672//'.format(
                user=broker_user,
                password=broker_pass,
            ),
            daemon.broker_url,
        )

    @patch('cloudify_agent.api.pm.base.os.makedirs')
    def test_broker_url_with_ssl_port(self, mock_os):
        daemon_args = copy(self.default_daemon_args)
        daemon_args.update({
            'broker_ssl_enabled': True,
            'workdir': '/not/a/real/path',
            # This will need to be a valid-ish cert when we start validating
            'broker_ssl_cert': 'notarealcert',
        })

        daemon = Daemon(**daemon_args)

        self.assertEqual('amqp://guest:guest@manager_ip:5671//',
                         daemon.broker_url)


class TestWriteBrokerConfig(BaseTest):

    # This MUST NOT include broker_user or broker_pass
    default_daemon_args = {
        'manager_ip': 'manager_ip',
        'name': 'name',
        'queue': 'queue',
        'workdir': '/not/a/real/path'
    }
    default_expected_config = {
        'broker_ssl_enabled': False,
        'broker_cert_path': '',
        'broker_username': 'guest',
        'broker_password': 'guest',
        'broker_hostname': 'manager_ip',
    }

    @patch('cloudify_agent.api.pm.base.os.makedirs')
    @patch('cloudify_agent.api.pm.base.open',
           create=True)
    @patch('cloudify_agent.api.pm.base.json')
    def test_default_security_settings(self, mock_json, mock_open, mock_os):
        daemon = Daemon(**self.default_daemon_args)

        daemon._create_celery_conf()

        mock_json.dump.assert_called_once_with(
            self.default_expected_config,
            mock_open().__enter__(),
        )

    @patch('cloudify_agent.api.pm.base.os.makedirs')
    @patch('cloudify_agent.api.pm.base.open',
           create=True)
    @patch('cloudify_agent.api.pm.base.json')
    def test_credentials_provided(self, mock_json, mock_open, mock_os):
        broker_user = 'testuser'
        broker_pass = 'cloudifytesting'

        daemon_args = copy(self.default_daemon_args)
        daemon_args.update({
            'broker_user': broker_user,
            'broker_pass': broker_pass,
        })

        daemon = Daemon(**daemon_args)

        daemon._create_celery_conf()

        expected_config = copy(self.default_expected_config)
        expected_config['broker_username'] = broker_user
        expected_config['broker_password'] = broker_pass

        mock_json.dump.assert_called_once_with(
            expected_config,
            mock_open().__enter__(),
        )

    @patch('cloudify_agent.api.pm.base.os.makedirs')
    @patch('cloudify_agent.api.pm.base.open',
           create=True)
    @patch('cloudify_agent.api.pm.base.json')
    def test_ssl_enabled(self, mock_json, mock_open, mock_os):
        cert_dir = '/not/a/real'
        cert_path = os.path.join('/not/a/real', 'broker.crt')

        daemon_args = copy(self.default_daemon_args)
        daemon_args.update({
            'broker_ssl_enabled': True,
            'workdir': cert_dir,
            # This will need to be a valid-ish cert when we start validating
            'broker_ssl_cert': 'notarealcert',
        })

        daemon = Daemon(**daemon_args)

        daemon._create_celery_conf()

        expected_config = copy(self.default_expected_config)
        expected_config['broker_ssl_enabled'] = True
        expected_config['broker_cert_path'] = cert_path

        mock_json.dump.assert_called_once_with(
            expected_config,
            mock_open().__enter__(),
        )
