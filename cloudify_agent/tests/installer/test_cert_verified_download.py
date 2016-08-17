#########
# Copyright (c) 2016 GigaSpaces Technologies Ltd. All rights reserved
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
import requests
import shutil
import subprocess
import tempfile

from mock import Mock


from cloudify_agent.tests.api.pm import only_ci, only_os
from unittest import TestCase

import nose.tools

from cloudify_agent.installer.runners.fabric_runner import (
    FabricRunner,
    FabricCommandExecutionException
)
from cloudify_agent.installer.runners.winrm_runner import WinRMRunner
from cloudify_agent.installer.linux import RemoteLinuxAgentInstaller
from cloudify_agent.installer.windows import RemoteWindowsAgentInstaller
from cloudify_agent.installer.operations import prepare_local_installer


from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import threading
import ssl


FABRIC_TEST_USER = 'cfy_agent_test'
FABRIC_TEST_PASSWORD = 'cfy_agent_test'


class HTTPSServer(HTTPServer):
    def __init__(self, certfile, keyfile, *args, **kwargs):
        self.certfile = certfile
        self.keyfile = keyfile
        HTTPServer.__init__(self, *args, **kwargs)

    def server_bind(self):
        with open(self.certfile) as f:
            print 'Starting with {0!r}'.format(f.read())
        self.socket = ssl.wrap_socket(self.socket, certfile=self.certfile,
                                      keyfile=self.keyfile,
                                      ssl_version=ssl.PROTOCOL_TLSv1)
        HTTPServer.server_bind(self)


class SimpleRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length', '3')
        self.end_headers()
        self.wfile.write(b'foo')


@nose.tools.nottest
class BaseInstallerDownloadTest(TestCase):
    def _make_cert(self):
        fd, cert_name = tempfile.mkstemp(prefix='cert-')
        self.addCleanup(os.unlink, cert_name)
        os.close(fd)
        fd, key_name = tempfile.mkstemp(prefix='key-')
        self.addCleanup(os.unlink, key_name)
        os.close(fd)
        openssl_args = ['openssl', 'req', '-x509', '-newkey', 'rsa:512',
                        '-nodes', '-subj', "/CN=localhost", '-keyout',
                        key_name, '-out', cert_name]

        if os.name == 'nt':
            openssl_args.extend([
                '-config',
                'C:\\OpenSSL-Win64\\bin\\openssl.cfg'
            ])

        subprocess.check_call(openssl_args)
        return cert_name, key_name

    def run_fileserver(self, certfile, keyfile):
        server = HTTPSServer(certfile, keyfile, ('', 0),
                             SimpleRequestHandler)
        t = threading.Thread(target=server.serve_forever)
        t.start()
        return server

    def setUp(self):
        self.certfile, self.keyfile = self._make_cert()
        with open(self.certfile) as f:
            self.cert_content = f.read()
        self._server = self.run_fileserver(self.certfile, self.keyfile)
        self.addCleanup(self._server.shutdown)

    def make_runner(self):
        raise NotImplementedError('Must be implemented by sub-class')

    @property
    def installer_cls(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def make_installer(self, cloudify_agent):
        runner = self.make_runner()
        return self.installer_cls(cloudify_agent, runner)

    def _do_download(self, installer):
        return installer.download('https://localhost:{0}'.format(
            self._server.server_port))

    def check_download(self, installer, should_fail):
        try:
            downloaded_file = self._do_download(installer)
        except requests.exceptions.SSLError:
            if should_fail:
                return
            raise
        else:
            if should_fail:
                self.fail('Cert should have not been verified')

        self.addCleanup(os.unlink, downloaded_file)
        self.assertTrue(os.path.exists(downloaded_file))
        with open(downloaded_file) as f:
            self.assertEqual('foo', f.read())

    def _expanduser(self, path):
        return os.path.expanduser(path)

    def _run_test(self, cloudify_agent, should_fail=False):
        cert_path = cloudify_agent['agent_rest_cert_path']
        cert_dir = os.path.dirname(self._expanduser(cert_path))
        installer = self.make_installer(cloudify_agent)

        self.addCleanup(shutil.rmtree, cert_dir)
        installer.upload_certificate()

        self.check_download(installer, should_fail)

    @only_ci
    def test_create_dir_upload_cert(self):
        cloudify_agent = {
            'agent_rest_cert_path': '~/certs/rest.pem',
            'rest_cert_content': self.cert_content,
            'verify_rest_certificate': True,
            'windows': os.name == 'nt'
        }

        self._run_test(cloudify_agent)

    @only_ci
    def test_preexisting_cert(self):
        cert_path = '~/certs/rest.pem'
        cloudify_agent = {
            'agent_rest_cert_path': cert_path,
            'rest_cert_content': 'invalid',
            'verify_rest_certificate': True,
            'windows': os.name == 'nt'
        }
        os.makedirs(os.path.dirname(self._expanduser(cert_path)))
        with open(self._expanduser(cert_path), 'wb') as f:
            f.write(self.cert_content)
        self._run_test(cloudify_agent)

    @only_ci
    def test_invalid_cert(self):
        cloudify_agent = {
            'agent_rest_cert_path': '~/certs/rest.pem',
            'rest_cert_content': 'invalid',
            'verify_rest_certificate': True,
            'windows': os.name == 'nt'
        }

        self._run_test(cloudify_agent, should_fail=True)


@nose.tools.istest
@only_os('posix')
class FabricInstallerTest(BaseInstallerDownloadTest):
    installer_cls = RemoteLinuxAgentInstaller

    def make_runner(self):
        logger = Mock()
        return FabricRunner(
            host='localhost',
            port=22,
            user=FABRIC_TEST_USER,
            password=FABRIC_TEST_PASSWORD,
            logger=logger
        )

    @classmethod
    def setUpClass(cls):
        from celery.contrib import rdb
        rdb.set_trace()
        import crypt
        subprocess.check_call([
            'sudo', 'useradd', '-p', crypt.crypt(FABRIC_TEST_PASSWORD, '22'),
            '-m', FABRIC_TEST_USER
        ])

    @classmethod
    def tearDownClass(cls):
        subprocess.check_call(['sudo', 'userdel', '-fr', FABRIC_TEST_USER])

    def _expanduser(self, path):
        return path.replace('~', '/home/{0}'.format(FABRIC_TEST_USER))

    def _do_download(self, installer):
        try:
            return installer.download('https://localhost:{0}'.format(
                self._server.server_port))
        except FabricCommandExecutionException:
            raise requests.exceptions.SSLError()


@nose.tools.istest
class LocalInstallerTest(BaseInstallerDownloadTest):
    def make_installer(self, cloudify_agent):
        return prepare_local_installer(cloudify_agent)


@nose.tools.istest
@only_os('nt')
class WinRMInstallerTest(BaseInstallerDownloadTest):
    installer_cls = RemoteWindowsAgentInstaller

    def make_runner(self):
        return WinRMRunner(
            host='localhost',
            port=5985,
            user='test_user',
            password='Pass@word1',
            logger=Mock()
        )
