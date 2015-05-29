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

from mock import patch
from mock import MagicMock

from cloudify_agent import VIRTUALENV
from cloudify_agent.shell.main import get_logger
from cloudify_agent.tests.shell.commands import BaseCommandLineTestCase
from cloudify_agent.tests import get_storage_directory


@patch('cloudify_agent.api.utils.get_storage_directory',
       get_storage_directory)
@patch('cloudify_agent.api.plugins.installer.PluginInstaller.install')
@patch('cloudify_agent.api.plugins.installer.PluginInstaller.uninstall')
@patch('cloudify_agent.shell.commands.plugins.DaemonFactory.load_all')
@patch('cloudify_agent.shell.commands.plugins.DaemonFactory.save')
class TestConfigureCommandLine(BaseCommandLineTestCase):

    def test_install(self, save, load_all, _, mock_install):
        daemon1 = MagicMock()
        daemon1.virtualenv = VIRTUALENV
        daemon2 = MagicMock()
        daemon2.virtualenv = VIRTUALENV
        load_all.return_value = [daemon1, daemon2]
        self._run('cfy-agent plugins install --source=source --args=args')
        mock_install.assert_called_once_with('source', 'args')
        load_all.assert_called_once_with(logger=get_logger())
        daemons = load_all.return_value
        for daemon in daemons:
            register = daemon.register
            register.assert_called_once_with(mock_install.return_value)

        self.assertEqual(save.call_count, 2)

    def test_uninstall(self, save, load_all, mock_uninstall, _):
        daemon1 = MagicMock()
        daemon1.virtualenv = VIRTUALENV
        daemon2 = MagicMock()
        daemon2.virtualenv = VIRTUALENV
        load_all.return_value = [daemon1, daemon2]
        self._run('cfy-agent plugins uninstall --plugin=plugin')
        mock_uninstall.assert_called_once_with('plugin')
        load_all.assert_called_once_with(logger=get_logger())
        daemons = load_all.return_value
        for daemon in daemons:
            unregister = daemon.unregister
            unregister.assert_called_once_with('plugin')

        self.assertEqual(save.call_count, 2)
