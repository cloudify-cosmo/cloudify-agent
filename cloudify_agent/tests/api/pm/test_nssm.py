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
import nose.tools
from mock import patch, Mock

from cloudify.exceptions import CommandExecutionException

from cloudify_agent.tests import BaseTest
from cloudify_agent.api.pm.nssm import NonSuckingServiceManagerDaemon
from cloudify_agent.tests.api.pm import BaseDaemonProcessManagementTest
from cloudify_agent.tests.api.pm import only_os
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.internal.get_storage_directory',
       get_storage_directory)
@nose.tools.istest
@only_os('nt')
class TestNonSuckingServiceManagerDaemon(BaseDaemonProcessManagementTest):

    @property
    def daemon_cls(self):
        return NonSuckingServiceManagerDaemon

    def test_configure(self):
        daemon = self.create_daemon()
        daemon.create()

        daemon.configure()
        self.assertTrue(os.path.exists(daemon.config_path))

    def test_delete(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.stop()
        daemon.delete()
        self.assertFalse(os.path.exists(daemon.config_path))
        self.assertRaises(
            CommandExecutionException,
            self.runner.run,
            'sc getdisplayname {0}'.format(daemon.name))


class TestNonSuckingServiceManagerDaemonComponents(BaseTest):
    default_daemon_args = {
        'manager_ip': 'manager_ip',
        'name': 'name',
        'queue': 'queue',
        'workdir': '/not/a/real/path'
    }

    @patch('cloudify_agent.api.pm.nssm.utils')
    @patch('cloudify_agent.api.pm.base.os.makedirs')
    def test_configure_creates_ssl_cert(self, mock_os, mock_utils):
        daemon = NonSuckingServiceManagerDaemon(**self.default_daemon_args)

        daemon._create_env_string = Mock()
        daemon._runner = Mock()
        daemon.register = Mock()
        daemon._create_ssl_cert = Mock()
        daemon._create_celery_conf = Mock()

        daemon.configure()

        daemon._create_ssl_cert.assert_called_once_with()

    @patch('cloudify_agent.api.pm.nssm.utils')
    @patch('cloudify_agent.api.pm.base.os.makedirs')
    def test_configure_creates_celery_config(self, mock_os, mock_utils):
        daemon = NonSuckingServiceManagerDaemon(**self.default_daemon_args)

        daemon._create_env_string = Mock()
        daemon._runner = Mock()
        daemon.register = Mock()
        daemon._create_ssl_cert = Mock()
        daemon._create_celery_conf = Mock()

        daemon.configure()

        daemon._create_celery_conf.assert_called_once_with()

    @patch('cloudify_agent.api.pm.nssm.utils.content_to_file')
    @patch('cloudify_agent.api.pm.base.os.makedirs')
    def test_rendered_template_refers_to_config(self, mock_os, mock_writer):
        daemon = NonSuckingServiceManagerDaemon(**self.default_daemon_args)

        daemon._create_env_string = Mock()
        daemon._runner = Mock()
        daemon.register = Mock()
        daemon._create_ssl_cert = Mock()
        daemon._create_celery_conf = Mock()

        daemon.configure()

        # We don't care about most of the args but there should only have been
        # one call, with ssl configured
        self.assertEqual(1, mock_writer.call_count)

        # Get the rendered content
        writer_args, _ = mock_writer.call_args
        rendered_file = writer_args[0]

        self.assertIn(
            '--config=cloudify.broker_config',
            rendered_file,
        )
