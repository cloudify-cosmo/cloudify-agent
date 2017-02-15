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
import sys
import logging
import tempfile
import getpass
import shutil

import unittest2 as unittest

from cloudify import constants, mocks
from cloudify.state import current_ctx
from cloudify.utils import setup_logger
import cloudify_agent.shell.env as env_constants

from cloudify_agent.api import defaults


try:
    win_error = WindowsError
except NameError:
    win_error = None


def get_storage_directory(_=None):
    return os.path.join(tempfile.gettempdir(), 'cfy-agent-tests-daemons')


class BaseTest(unittest.TestCase):

    agent_env_vars = {
        constants.MANAGER_FILE_SERVER_URL_KEY: 'localhost',
        constants.REST_HOST_KEY: 'localhost',
        constants.FILE_SERVER_HOST_KEY: 'localhost',
        constants.FILE_SERVER_PROTOCOL_KEY: 'http',
        constants.FILE_SERVER_PORT_KEY: '53229',
        constants.SECURITY_ENABLED_KEY: 'False',
        constants.REST_PROTOCOL_KEY: 'http',
        constants.REST_PORT_KEY: '80',
        constants.REST_CERT_CONTENT_KEY: '',
        constants.VERIFY_REST_CERTIFICATE_KEY: '',
        constants.AGENT_REST_CERT_PATH: 'rest/cert/path',
        constants.BROKER_SSL_CERT_PATH: 'broker/cert/path',
        env_constants.CLOUDIFY_AGENT_REST_CERT_PATH: 'rest/cert/path',
        env_constants.CLOUDIFY_BROKER_SSL_CERT_PATH: 'broker/cert/path'
    }

    def setUp(self):

        # change levels to 'DEBUG' to troubleshoot.
        self.logger = setup_logger(
            'cloudify-agent.tests',
            logger_level=logging.INFO)
        from cloudify_agent.api import utils
        utils.logger.setLevel(logging.INFO)

        self.curr_dir = os.getcwd()
        self.temp_folder = tempfile.mkdtemp(prefix='cfy-agent-tests-')
        for key, value in self.agent_env_vars.iteritems():
            os.environ[key] = value

        def clean_temp_folder():
            try:
                shutil.rmtree(self.temp_folder)
            except win_error:
                # no hard feeling if file is locked.
                pass

        def clean_env():
            for var in self.agent_env_vars.iterkeys():
                del os.environ[var]

        self.addCleanup(clean_temp_folder)
        self.addCleanup(clean_env)
        os.chdir(self.temp_folder)
        self.addCleanup(lambda: os.chdir(self.curr_dir))

        self.username = getpass.getuser()
        self.logger.info('Working directory: {0}'.format(self.temp_folder))

        self.mock_ctx_with_tenant()

    def mock_ctx_with_tenant(self):
        self.original_ctx = current_ctx
        current_ctx.set(mocks.MockContext({'tenant_name': 'default_tenant'}))
        self.addCleanup(self._restore_ctx)

    def _restore_ctx(self):
        current_ctx.set(self.original_ctx)


class _AgentPackageGenerator(object):

    def __init__(self):
        self.initialized = False

    def _initialize(self):
        from cloudify_agent.tests import utils
        self._resources_dir = tempfile.mkdtemp(
            prefix='file-server-resource-base')
        self._fs = utils.FileServer(
            root_path=self._resources_dir, port=8888)
        self._fs.start()
        config = {
            'cloudify_agent_module': utils.get_source_uri(),
            'requirements_file': utils.get_requirements_uri(),
            'python_path': os.path.join(
                getattr(sys, 'real_prefix', sys.prefix), 'bin', 'python'),
        }
        package_name = utils.create_agent_package(self._resources_dir, config)
        self._package_url = 'http://localhost:{0}/{1}'.format(
            self._fs.port, package_name)
        self._package_path = os.path.join(self._resources_dir, package_name)
        self.initialized = True

    def get_package_url(self):
        if not self.initialized:
            self._initialize()
        return self._package_url

    def get_package_path(self):
        if not self.initialized:
            self._initialize()
        return self._package_path

    def cleanup(self):
        if self.initialized:
            self._fs.stop()
            shutil.rmtree(self._resources_dir)
            self.initialized = False


class _AgentSSLCert(object):
    LOCAL_CERT_FILE = None
    DUMMY_CERT = '-----BEGIN RSA PRIVATE KEY-----\n' \
                 'Fn0TToW05rmMrO0XT092R/JqFZBX9ygpaBy8y14o0bX9jA6neFT8sUgDCd' \
                 'mTmGoq\nQSeUzP4gEUxuJZ373+7HK565FohtWUUvBshgCA/o+WIH/szN/x' \
                 'W0f+m4lshT6hXB\nz86ktJFvgaBe9f1rBFG4Q1vGDSmylHfGxn7yYljJ5K' \
                 'tKRdngpnEeWr0VQ3wJ+ri8\n' \
                 '-----END RSA PRIVATE KEY-----'

    @staticmethod
    def get_local_cert_path():
        if not _AgentSSLCert.LOCAL_CERT_FILE:
            _, _AgentSSLCert.LOCAL_CERT_FILE = tempfile.mkstemp()
            with open(_AgentSSLCert.LOCAL_CERT_FILE, 'w') as f:
                f.write(_AgentSSLCert.DUMMY_CERT)

        return _AgentSSLCert.LOCAL_CERT_FILE

    @staticmethod
    def verify_remote_cert(agent_dir):
        agent_cert_path = os.path.join(
            os.path.expanduser(agent_dir),
            os.path.normpath(defaults.SSL_CERTS_TARGET_DIR),
            defaults.AGENT_SSL_CERT_FILENAME
        )
        with open(agent_cert_path, 'r') as f:
            cert_content = f.read().strip()

        assert cert_content == _AgentSSLCert.DUMMY_CERT


agent_package = _AgentPackageGenerator()
agent_ssl_cert = _AgentSSLCert()


def tearDown():
    agent_package.cleanup()
