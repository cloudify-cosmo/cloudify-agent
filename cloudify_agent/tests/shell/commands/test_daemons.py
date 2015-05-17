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

import logging

from mock import patch

from cloudify_agent.api import utils
from cloudify_agent.tests.shell.commands import BaseCommandLineTestCase
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.get_storage_directory',
       get_storage_directory)
@patch('cloudify_agent.shell.commands.daemons.DaemonFactory')
class TestPatchedDaemonCommandLine(BaseCommandLineTestCase):

    PROCESS_MANAGEMENT = 'init.d'

    def test_create(self, factory):
        self._run('cfy-agent daemons create --name=name '
                  '--process-management=init.d '
                  '--queue=queue --manager-ip=127.0.0.1 --user=user ')

        factory_new = factory.new
        factory_new.assert_called_once_with(
            name='name',
            queue='queue',
            user='user',
            manager_ip='127.0.0.1',
            process_management='init.d',
            broker_ip=None,
            workdir=None,
            broker_url=None,
            max_workers=None,
            min_workers=None,
            broker_port=None,
            manager_port=None,
            extra_env_path=None,
            logger_level=logging.INFO
        )

        daemon = factory_new.return_value
        daemon.create.assert_called_once_with()

    def test_create_with_custom_options(self, factory):
        self._run('cfy-agent daemons create --name=name '
                  '--queue=queue --manager-ip=127.0.0.1 --user=user '
                  '--process-management=init.d '
                  '--key=value --complex-key=complex-value')

        factory_new = factory.new
        factory_new.assert_called_once_with(
            name='name',
            queue='queue',
            user='user',
            manager_ip='127.0.0.1',
            process_management='init.d',
            broker_ip=None,
            workdir=None,
            broker_url=None,
            max_workers=None,
            min_workers=None,
            broker_port=None,
            manager_port=None,
            extra_env_path=None,
            logger_level=logging.INFO,
            key='value',
            complex_key='complex-value'
        )

    def test_configure(self, factory):
        self._run('cfy-agent daemons configure --name=name ')

        factory_load = factory.load
        factory_load.assert_called_once_with('name',
                                             logger_level=logging.INFO)

        daemon = factory_load.return_value
        daemon.configure.assert_called_once_with()

    def test_start(self, factory):
        self._run('cfy-agent daemons start --name=name '
                  '--interval 5 --timeout 20 --delete-amqp-queue')

        factory_load = factory.load
        factory_load.assert_called_once_with('name',
                                             logger_level=logging.INFO)

        daemon = factory_load.return_value
        daemon.start.assert_called_once_with(
            interval=5,
            timeout=20,
            delete_amqp_queue=True,
        )

    def test_stop(self, factory):
        self._run('cfy-agent daemons stop --name=name '
                  '--interval 5 --timeout 20')

        factory_load = factory.load
        factory_load.assert_called_once_with('name',
                                             logger_level=logging.INFO)

        daemon = factory_load.return_value
        daemon.stop.assert_called_once_with(
            interval=5,
            timeout=20
        )

    def test_delete(self, factory):
        self._run('cfy-agent daemons delete --name=name')

        factory_load = factory.load
        factory_load.assert_called_once_with('name',
                                             logger_level=logging.INFO)

        daemon = factory_load.return_value
        daemon.delete.assert_called_once_with()

    def test_restart(self, factory):
        self._run('cfy-agent daemons restart --name=name')

        factory_load = factory.load
        factory_load.assert_called_once_with('name',
                                             logger_level=logging.INFO)

        daemon = factory_load.return_value
        daemon.restart.assert_called_once_with()

    def test_register(self, factory):
        self._run('cfy-agent daemons register '
                  '--name=name --plugin=plugin')

        factory_load = factory.load
        factory_load.assert_called_once_with('name', logger_level=logging.INFO)

        daemon = factory_load.return_value
        daemon.register.assert_called_once_with('plugin')

    @patch('cloudify_agent.shell.commands.daemons.api_utils.daemon_to_dict')
    def test_inspect(self, daemon_to_dict, factory):

        name = utils.generate_agent_name()
        self._run('cfy-agent daemons inspect --name={0}'.format(name))

        factory_load = factory.load
        factory_load.assert_called_once_with(name)
        daemon = factory_load.return_value

        daemon_to_dict.assert_called_once_with(daemon)

    def test_required(self, _):
        self._run('cfy-agent daemons create --manager-ip=manager '
                  '--process-management=init.d', raise_system_exit=True)


@patch('cloudify_agent.api.utils.get_storage_directory',
       get_storage_directory)
@patch('cloudify_agent.shell.commands.daemons.api_utils.get_storage_directory',
       get_storage_directory)
class TestDaemonCommandLine(BaseCommandLineTestCase):

    def test_inspect_non_existing_agent(self):
        try:
            self._run('cfy-agent daemons inspect --name=non-existing',
                      raise_system_exit=True)
        except SystemExit as e:
            self.assertEqual(e.code, 203)

    def test_list(self):
        self._run('cfy-agent daemons create '
                  '--process-management=init.d '
                  '--queue=queue --manager-ip=127.0.0.1 --user=user ')
        self._run('cfy-agent daemons create '
                  '--process-management=init.d '
                  '--queue=queue --manager-ip=127.0.0.1 --user=user ')
        self._run('cfy-agent daemons list')
