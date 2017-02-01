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

from cloudify.state import current_ctx
from cloudify.mocks import MockCloudifyContext
from cloudify import utils as cloudify_utils
from cloudify import exceptions

from cloudify_agent.installer import script
from cloudify_agent.tests import BaseTest, utils, agent_ssl_cert
from cloudify_agent.tests.api.pm import only_os


class BaseInitScriptTest(BaseTest):

    windows = None

    def _serve(self):
        self.port = 5555
        self.server = utils.FileServer(self.temp_folder, port=self.port)
        self.server.start()
        self.addCleanup(lambda: self.server.stop())

    def setUp(self):
        super(BaseInitScriptTest, self).setUp()
        ctx = MockCloudifyContext(
            node_id='d',
            properties={'agent_config': {
                'user': self.username,
                'install_method': 'init_script',
                'rest_host': 'localhost',
                'windows': self.windows,
                'basedir': self.temp_folder
            }})
        current_ctx.set(ctx)

        self.addCleanup(lambda: current_ctx.clear())
        self.input_cloudify_agent = {
            'broker_ip': 'localhost',
            'ssl_cert_path': agent_ssl_cert.get_local_cert_path()
        }

    def _run(self, *commands):
        init_script = script.init_script(
            cloudify_agent=self.input_cloudify_agent)
        init_script = '\n'.join(init_script.split('\n')[:-1])
        if self.windows:
            init_script_path = os.path.abspath('init_script.ps1')
        else:
            init_script_path = os.path.abspath('init_script.sh')
        with open(init_script_path, 'w') as f:
            f.write(init_script)
            for command in commands:
                f.write('{0}\n'.format(command))
        if not self.windows:
            os.chmod(init_script_path, 0755)
        if self.windows:
            command_line = 'powershell {0}'.format(init_script_path)
        else:
            command_line = init_script_path
        runner = cloudify_utils.LocalCommandRunner(self.logger)
        response = runner.run(command_line)
        return response.std_out


@only_os('posix')
class TestLinuxInitScript(BaseInitScriptTest):

    def setUp(self):
        self.windows = False
        super(TestLinuxInitScript, self).setUp()

    def test_download_curl(self):
        self._serve()
        self._run('ln -s $(which curl) curl',
                  'PATH=$PWD',
                  'download http://localhost:{0} download.output'.format(
                      self.port))
        self.assertTrue(os.path.isfile('download.output'))

    def test_download_wget(self):
        self._serve()
        self._run('ln -s $(which wget) wget',
                  'PATH=$PWD',
                  'download http://localhost:{0} download.output'.format(
                      self.port))
        self.assertTrue(os.path.isfile('download.output'))

    def test_download_no_curl_or_wget(self):
        self._serve()
        self.assertRaises(
            exceptions.CommandExecutionException,
            self._run,
            'PATH=$PWD',
            'download http://localhost:{0} download.output'.format(self.port))

    def test_package_url_implicit(self):
        output = self._run('package_url')
        self.assertIn('-agent.tar.gz', output)

    def test_package_url_explicit(self):
        self.input_cloudify_agent.update({
            'distro': 'one',
            'distro_codename': 'two'
        })
        output = self._run('package_url')
        self.assertIn('one-two-agent.tar.gz', output)

    def test_create_custom_env_file(self):
        self.input_cloudify_agent.update({'env': {'one': 'one'}})
        self._run('create_custom_env_file')
        with open('custom_agent_env.sh') as f:
            self.assertIn('export one=one', f.read())

    def test_no_create_custom_env_file(self):
        self._run('create_custom_env_file')
        self.assertFalse(os.path.isfile('custom_agent_env.sh'))

    def test_create_ssl_cert(self):
        self._run('add_ssl_cert')
        agent_ssl_cert.verify_remote_cert(
            self.input_cloudify_agent['agent_dir']
        )


@only_os('nt')
class TestWindowsInitScript(BaseInitScriptTest):

    def setUp(self):
        self.windows = True
        super(TestWindowsInitScript, self).setUp()

    def test_create_custom_env_file(self):
        self.input_cloudify_agent.update({'env': {'one': 'one'}})
        self._run('CreateCustomEnvFile')
        with open('custom_agent_env.bat') as f:
            self.assertIn('set one=one', f.read())

    def test_no_create_custom_env_file(self):
        self._run('CreateCustomEnvFile')
        self.assertFalse(os.path.isfile('custom_agent_env.bat'))

    def test_create_ssl_cert(self):
        self._run('AddSSLCert')
        agent_ssl_cert.verify_remote_cert(
            self.input_cloudify_agent['agent_dir']
        )
