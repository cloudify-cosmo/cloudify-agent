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

from mock import patch
import pytest

from cloudify.state import current_ctx
from cloudify import utils as cloudify_utils
from cloudify import constants, exceptions

from cloudify_agent.installer import script
from cloudify_agent.tests import BaseTest, utils, agent_ssl_cert
from cloudify_agent.tests.api.pm import only_os
from cloudify_agent.tests.installer.config import mock_context


class BaseInstallScriptTest(BaseTest):

    windows = None

    def _serve(self):
        self.server = utils.FileServer(self.temp_folder, ssl=False)
        self.server.start()
        self.addCleanup(self.server.stop)

    def setUp(self):
        super(BaseInstallScriptTest, self).setUp()
        self._set_mock_context()
        self.addCleanup(current_ctx.clear)
        self.input_cloudify_agent = {
            'broker_ip': 'localhost',
            'ssl_cert_path': self._rest_cert_path
        }

    def _set_mock_context(self, **override_properties):
        node_properties = {
            'agent_config': {
                'user': self.username,
                'install_method': 'init_script',
                'rest_host': 'localhost',
                'windows': self.windows,
                'basedir': self.temp_folder
            }
        }
        node_properties['agent_config'].update(**override_properties)
        current_ctx.set(mock_context(node_id='d', properties=node_properties))

    def _get_install_script(self, add_ssl_cert=True):
        with patch.dict(os.environ, {constants.MANAGER_NAME: 'cloudify'}):
            script_builder = script._get_script_builder(
                cloudify_agent=self.input_cloudify_agent
            )
            return script_builder.install_script(add_ssl_cert=add_ssl_cert)

    def _run(self, *commands):
        install_script = self._get_install_script()

        # Remove last line where main function is executed
        install_script = '\n'.join(install_script.split('\n')[:-1])

        if self.windows:
            install_script_path = os.path.abspath('install_script.ps1')
        else:
            install_script_path = os.path.abspath('install_script.sh')
        with open(install_script_path, 'w') as f:
            f.write(install_script)
            # Inject test commands
            f.write('\n{0}'.format('\n'.join(commands)))

        if not self.windows:
            os.chmod(install_script_path, 0o755)
        if self.windows:
            command_line = 'powershell {0}'.format(install_script_path)
        else:
            command_line = install_script_path
        runner = cloudify_utils.LocalCommandRunner(self.logger)
        response = runner.run(command_line)
        return response.std_out


@only_os('posix')
class TestLinuxInstallScript(BaseInstallScriptTest):
    windows = False

    def test_download_curl(self):
        self._serve()
        self._run('ln -s $(which curl) curl',
                  'PATH=$PWD',
                  'download http://localhost:{0} download.output'
                  .format(self.server.port))
        assert os.path.isfile('download.output')

    def test_download_wget(self):
        self._serve()
        self._run('ln -s $(which wget) wget',
                  'PATH=$PWD',
                  'download http://localhost:{0} download.output'
                  .format(self.server.port))
        assert os.path.isfile('download.output')

    def test_download_no_curl_or_wget(self):
        self._serve()
        pytest.raises(
            exceptions.CommandExecutionException,
            self._run,
            'PATH=$PWD',
            'download http://localhost:{0} download.output'
            .format(self.server.port),
        )

    def test_package_url_implicit(self):
        output = self._run('package_url')
        assert '-agent.tar.gz' in output

    def test_package_url_explicit(self):
        self.input_cloudify_agent.update({
            'distro': 'one',
            'distro_codename': 'two'
        })
        output = self._run('package_url')
        assert 'one-two-agent.tar.gz' in output

    def test_create_custom_env_file(self):
        self.input_cloudify_agent.update({'env': {'one': 'one'}})
        self._run('create_custom_env_file')
        with open('custom_agent_env.sh') as f:
            assert 'export one="one"' in f.read()

    def test_no_create_custom_env_file(self):
        self._run('create_custom_env_file')
        assert not os.path.isfile('custom_agent_env.sh')

    def test_create_ssl_cert(self):
        self._run('add_ssl_cert')
        # basedir + node_id
        agent_dir = os.path.join(self.temp_folder, 'd')
        agent_ssl_cert.verify_remote_cert(agent_dir)

    def test_add_ssl_func_not_rendered(self):
        install_script = self._get_install_script(add_ssl_cert=False)
        assert 'add_ssl_cert' not in install_script

    def test_install_is_rendered_by_default(self):
        install_script = self._get_install_script()
        assert 'install_agent' in install_script

    def test_install_not_rendered_in_provided_mode(self):
        self._set_mock_context(install_method='provided')
        install_script = self._get_install_script()
        assert 'install_agent' not in install_script


@only_os('nt')
class TestWindowsInstallScript(BaseInstallScriptTest):
    windows = True

    def test_create_custom_env_file(self):
        self.input_cloudify_agent.update({'env': {'one': 'one'}})
        self._run('CreateCustomEnvFile')
        with open('custom_agent_env.bat') as f:
            assert 'set one="one"' in f.read()

    def test_no_create_custom_env_file(self):
        self._run('CreateCustomEnvFile')
        assert not os.path.isfile('custom_agent_env.bat')

    def test_create_ssl_cert(self):
        self._run('AddSSLCert')
        # basedir + node_id
        agent_dir = os.path.join(self.temp_folder, 'd')
        agent_ssl_cert.verify_remote_cert(agent_dir)

    def test_add_ssl_func_not_rendered(self):
        install_script = self._get_install_script(add_ssl_cert=False)
        assert 'AddSSLCert' not in install_script

    def test_install_not_rendered_in_provided_mode(self):
        self._set_mock_context(install_method='provided')
        install_script = self._get_install_script()
        assert 'InstallAgent' not in install_script
