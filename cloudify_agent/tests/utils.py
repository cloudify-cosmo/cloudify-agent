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

import filecmp
import os
import platform
import ssl
import tarfile
import tempfile
import threading
import uuid
import wsgiref.simple_server
from contextlib import contextmanager

import bottle
import wagon
from agent_packager import packager

from cloudify.exceptions import NonRecoverableError
from cloudify.utils import LocalCommandRunner
from cloudify.utils import setup_logger

import cloudify_agent

from cloudify_agent.tests import resources
from cloudify_agent.api.defaults import (SSL_CERTS_TARGET_DIR,
                                         AGENT_SSL_CERT_FILENAME)


logger = setup_logger('cloudify_agent.tests.utils')


@contextmanager
def env(key, value):
    os.environ[key] = value
    yield
    del os.environ[key]


def create_mock_plugin(basedir, install_requires=None):
    install_requires = install_requires or []
    name = str(uuid.uuid4())
    plugin_dir = os.path.join(basedir, name)
    setup_py = os.path.join(plugin_dir, 'setup.py')
    os.mkdir(plugin_dir)
    with open(setup_py, 'w') as f:
        f.write('from setuptools import setup; '
                'setup(name="{0}", install_requires={1}, version="0.1")'
                .format(name, install_requires))
    return name


def create_plugin_tar(plugin_dir_name,
                      target_directory,
                      basedir=None):

    """
    Create a tar file from the plugin.

    :param plugin_dir_name: the plugin directory name, relative to the
    resources package.
    :type plugin_dir_name: str
    :param target_directory: the directory to create the tar in
    :type target_directory: str

    :return: the name of the create tar, note that this is will just return
    the base name, not the full path to the tar.
    :rtype: str
    """

    if basedir:
        plugin_source_path = os.path.join(basedir, plugin_dir_name)
    else:
        plugin_source_path = resources.get_resource(os.path.join(
            'plugins', plugin_dir_name))

    plugin_tar_file_name = '{0}.tar'.format(plugin_dir_name)
    target_tar_file_path = os.path.join(target_directory,
                                        plugin_tar_file_name)

    plugin_tar_file = tarfile.TarFile(target_tar_file_path, 'w')
    try:
        plugin_tar_file.add(plugin_source_path, plugin_dir_name)
    finally:
        plugin_tar_file.close()

    return plugin_tar_file_name


def create_plugin_wagon(plugin_dir_name,
                        target_directory,
                        requirements=False,
                        basedir=None):

    """
    Create a wagon from a plugin.

    :param plugin_dir_name: the plugin directory name, relative to the
    resources package.
    :type plugin_dir_name: str
    :param target_directory: the directory to create the wagon in
    :type target_directory: str
    :param requirements: optional requirements for wagon
    :type requirements: str

    :return: path to created wagon`
    :rtype: str
    """
    if basedir:
        plugin_source_path = os.path.join(basedir, plugin_dir_name)
    else:
        plugin_source_path = resources.get_resource(os.path.join(
            'plugins', plugin_dir_name))
    return wagon.create(
        plugin_source_path,
        requirement_files=requirements,
        archive_destination_dir=target_directory
    )


def get_source_uri():
    return os.path.dirname(os.path.dirname(cloudify_agent.__file__))


def get_requirements_uri():
    return os.path.join(get_source_uri(), 'dev-requirements.txt')


# This should be integrated into packager
# For now, this is the best place
def create_windows_installer(config, logger):
    runner = LocalCommandRunner()
    wheelhouse = resources.get_resource('winpackage/source/wheels')

    pip_cmd = 'pip wheel --wheel-dir {wheel_dir} --requirement {req_file}'.\
        format(wheel_dir=wheelhouse, req_file=config['requirements_file'])

    logger.info('Building wheels into: {0}'.format(wheelhouse))
    runner.run(pip_cmd)

    pip_cmd = 'pip wheel --find-links {wheel_dir} --wheel-dir {wheel_dir} ' \
              '{repo_url}'.format(wheel_dir=wheelhouse,
                                  repo_url=config['cloudify_agent_module'])
    runner.run(pip_cmd)

    iscc_cmd = 'C:\\Program Files (x86)\\Inno Setup 5\\iscc.exe {0}'\
        .format(resources.get_resource(
            os.path.join('winpackage', 'create.iss')))
    os.environ['VERSION'] = '0'
    os.environ['iscc_output'] = os.getcwd()
    runner.run(iscc_cmd)


def create_agent_package(directory, config, package_logger=None):
    if package_logger is None:
        package_logger = logger
    package_logger.info('Changing directory into {0}'.format(directory))
    original = os.getcwd()
    try:
        package_logger.info('Creating Agent Package')
        os.chdir(directory)
        if platform.system() == 'Linux':
            packager.create(config=config,
                            config_file=None,
                            force=False,
                            verbose=False)
            distname, _, distid = platform.dist()
            return '{0}-{1}-agent.tar.gz'.format(distname, distid)
        elif platform.system() == 'Windows':
            create_windows_installer(config, logger)
            return 'cloudify_agent_0.exe'
        else:
            raise NonRecoverableError('Platform not supported: {0}'
                                      .format(platform.system()))
    finally:
        os.chdir(original)


def are_dir_trees_equal(dir1, dir2):

    """
    Compare two directories recursively. Files in each directory are
    assumed to be equal if their names and contents are equal.

    :param dir1: First directory path
    :type dir1: str
    :param dir2: Second directory path
    :type dir2: str

    :return: True if the directory trees are the same and
             there were no errors while accessing the directories or files,
             False otherwise.
    :rtype: bool
   """

    # compare file lists in both dirs. If found different lists
    # or "funny" files (failed to compare) - return false
    dirs_cmp = filecmp.dircmp(dir1, dir2)
    if len(dirs_cmp.left_only) > 0 or len(dirs_cmp.right_only) > 0 or \
            len(dirs_cmp.funny_files) > 0:
        return False

    # compare the common files between dir1 and dir2
    (match, mismatch, errors) = filecmp.cmpfiles(
        dir1, dir2, dirs_cmp.common_files, shallow=False)
    if len(mismatch) > 0 or len(errors) > 0:
        return False

    # continue to compare sub-directories, recursively
    for common_dir in dirs_cmp.common_dirs:
        new_dir1 = os.path.join(dir1, common_dir)
        new_dir2 = os.path.join(dir2, common_dir)
        if not are_dir_trees_equal(new_dir1, new_dir2):
            return False

    return True


class SSLWSGIServer(wsgiref.simple_server.WSGIServer):
    _certfile = None
    _keyfile = None

    def server_close(self):
        wsgiref.simple_server.WSGIServer.server_close(self)
        if self._certfile:
            os.unlink(self._certfile)
        if self._keyfile:
            os.unlink(self._keyfile)

    def get_request(self):
        if not self._certfile or not self._keyfile:
            self._certfile = _AgentSSLCert.get_local_cert_path()
            self._keyfile = _AgentSSLCert.local_key_path()
        socket, addr = wsgiref.simple_server.WSGIServer.get_request(self)
        socket = ssl.wrap_socket(
            socket, keyfile=self._keyfile, certfile=self._certfile,
            server_side=True)
        return socket, addr


class FileServer(object):
    def __init__(self, root_path=None, port=0, ssl=True):
        self._port = port
        self.root_path = root_path or os.path.dirname(resources.__file__)
        self._server = None
        self._server_thread = None
        self._ssl = ssl

    @property
    def port(self):
        if not self._server:
            return
        return self._server.server_address[1]

    def start(self, timeout=5):
        app = bottle.Bottle()

        @app.get('/')
        def get_index():
            return '\n'.join(os.listdir(self.root_path))

        @app.get('/<filename:path>')
        def get_file(filename):
            return bottle.static_file(filename, root=self.root_path)

        server_class = SSLWSGIServer if self._ssl else \
            wsgiref.simple_server.WSGIServer
        self._server = wsgiref.simple_server.make_server(
            '', self._port, app, server_class=server_class)

        self._server_thread = threading.Thread(
            target=self._server.serve_forever)
        self._server_thread.start()

    def stop(self, timeout=15):
        self._server.shutdown()
        self._server_thread.join(timeout)
        if self._server_thread.is_alive():
            raise RuntimeError('FileServer failed to stop')


def op_context(task_name,
               task_target='non-empty-value',
               deployment_id=None,
               plugin_name=None,
               package_name=None,
               package_version=None,
               execution_env=None,
               tenant_name='default_tenant'):
    result = {
        'type': 'operation',
        'task_name': task_name,
        'task_target': task_target,
        'tenant': {'name': tenant_name},
        'execution_env': execution_env,
        'plugin': {
            'name': plugin_name,
            'package_name': package_name,
            'package_version': package_version
        },
        # agents in tests do not have a manager
        'local': True
    }
    if deployment_id:
        result['deployment_id'] = deployment_id
    return result


class _AgentSSLCert(object):
    DUMMY_CERT = """-----BEGIN CERTIFICATE-----
MIIB9jCCAV+gAwIBAgIJAPSWQ5SpAsA1MA0GCSqGSIb3DQEBCwUAMBQxEjAQBgNV
BAMMCTEyNy4wLjAuMTAeFw0xOTA2MDcxMzI2MTVaFw0yMDA2MDYxMzI2MTVaMBQx
EjAQBgNVBAMMCTEyNy4wLjAuMTCBnzANBgkqhkiG9w0BAQEFAAOBjQAwgYkCgYEA
wxec40yt8nLAhCvQ564LB64aMhrQG5OeqXF+9Gf02goy41VBTZ+nCa98E6e3kbQc
syJR1BotgnJtR8hyYiw5svAkVue6dwxBtZ+zyH6WDQxmDnK3ilRCJeD5VdiDZfau
vQpgYGbTnm5PIm6ifNo2Sw4DOhf93TCZ/du5OvlihIUCAwEAAaNQME4wHQYDVR0O
BBYEFDjXfACluAhEgcX1ZFlNYlIAJLD5MB8GA1UdIwQYMBaAFDjXfACluAhEgcX1
ZFlNYlIAJLD5MAwGA1UdEwQFMAMBAf8wDQYJKoZIhvcNAQELBQADgYEAqwzTZFXJ
MrophVgsYCqPByU1aw2IulZGnocsbpRv1VQVxYQSo42JwQfu82DyG0rCXjAeaph6
Plo3XHZ0yvRmWVTb8pORbg+RQqzzFQmb7nhSpIaBMMim6u5G5/184dmCloc4QyWL
/CJQWsGXXUBg+8HNhzReKvdbICSTlqaonZo=
-----END CERTIFICATE-----"""
    PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGBAMMXnONMrfJywIQr
0OeuCweuGjIa0BuTnqlxfvRn9NoKMuNVQU2fpwmvfBOnt5G0HLMiUdQaLYJybUfI
cmIsObLwJFbnuncMQbWfs8h+lg0MZg5yt4pUQiXg+VXYg2X2rr0KYGBm055uTyJu
onzaNksOAzoX/d0wmf3buTr5YoSFAgMBAAECgYAg9Nk08Jwl68qnyTsWGCmW14tn
UW48aliQKTMYGIOdXcGw85L/iOvP0Aw2yctR2spKXI7UNMPhWHErgioIeY4ZZ4Qs
QaFB776YP1779aJjT98J/PMuWj+R3iTWm1jWngmCOgrCvRfTf8eV6EGee11zaiyT
ThvvEP2+gnGCTLHVwQJBAPJ3a+aIsPct8s+saWCUX7p6v25TXLWgzpPRh2KadXhw
FwS+6bQ4a41gfuRT54XhGXU5ICTz542ubwe+6qTjznUCQQDN+0P9BTOkLRTVFmTo
KsTIyfHaWVOIP55X5D7WHczunzTAHzDqFus0ebAB6Zvxb2u86JcT6jrkmF8HCLPZ
SjvRAkEArGyKWdWI6y5MxqxX/6tj7AvQSFeVzT++x9WwDknDEdO8Os69CUE6Er61
Xg/gzA8IeJkYJ88fMl0CbiKxYHLz5QJAERKaeAZOWXVDHMZWZsfkt5/FZAuzWL+t
KCvK6YRe0AhyHtp2+3Aa3qaXaBEs074gd+/vVb88UmYuui6GeaQlgQJATayT5T0D
ZW6ExLdmb9PCe6psBBCFMBgeBpcTQXKM2UvfZg6zovMRjd8fbjlTPJvxj9lfsjsc
12XFXMUqKqE6tw==
-----END PRIVATE KEY-----"""

    @staticmethod
    def get_local_cert_path(temp_folder=None):
        with tempfile.NamedTemporaryFile(delete=False, dir=temp_folder) as f:
            f.write(_AgentSSLCert.DUMMY_CERT)
        return f.name

    @staticmethod
    def local_key_path(temp_folder=None):
        with tempfile.NamedTemporaryFile(delete=False, dir=temp_folder) as f:
            f.write(_AgentSSLCert.PRIVATE_KEY)
        return f.name

    @staticmethod
    def _clean_cert(cert_content):
        """ Strip any whitespaces, and normalize the string on windows """

        cert_content = cert_content.strip()
        cert_content = cert_content.replace('\r\n', '\n').replace('\r', '\n')
        return cert_content

    @staticmethod
    def verify_remote_cert(agent_dir):
        agent_cert_path = os.path.join(
            os.path.expanduser(agent_dir),
            os.path.normpath(SSL_CERTS_TARGET_DIR),
            AGENT_SSL_CERT_FILENAME
        )
        with open(agent_cert_path, 'r') as f:
            cert_content = f.read()

        cert_content = _AgentSSLCert._clean_cert(cert_content)
        assert cert_content == _AgentSSLCert.DUMMY_CERT
