import filecmp
import os
import platform
import ssl
import tarfile
import threading
import wsgiref.simple_server
from contextlib import contextmanager

import bottle
import wagon
from agent_packager import packager

from cloudify.exceptions import NonRecoverableError
from cloudify.utils import LocalCommandRunner
from cloudify.utils import setup_logger

import cloudify_agent

from cloudify_agent.tests import random_id, resources
from cloudify_agent.api.defaults import (SSL_CERTS_TARGET_DIR,
                                         AGENT_SSL_CERT_FILENAME)


logger = setup_logger('cloudify_agent.tests.utils')


def get_daemon_storage(path):
    return os.path.join(path, 'daemon_storage')


@contextmanager
def env(key, value):
    os.environ[key] = value
    yield
    del os.environ[key]


def create_mock_plugin(basedir, install_requires=None):
    install_requires = install_requires or []
    name = 'plugin_' + random_id(with_prefix=False)
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
        format(wheel_dir=wheelhouse,
               req_file=config.get('install', 'requirements_file'))

    logger.info('Building wheels into: {0}'.format(wheelhouse))
    runner.run(pip_cmd)

    pip_cmd = 'pip wheel --find-links {wheel_dir} --wheel-dir {wheel_dir} ' \
              '{repo_url}'\
              .format(
                  wheel_dir=wheelhouse,
                  repo_url=config.get('install', 'cloudify_agent_module'))
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
        socket, addr = wsgiref.simple_server.WSGIServer.get_request(self)
        socket = ssl.wrap_socket(
            socket, keyfile=self._keyfile, certfile=self._certfile,
            server_side=True)
        return socket, addr


class FileServer(object):
    def __init__(self, agent_ssl_cert, root_path=None, ssl=True):
        self.certfile = agent_ssl_cert.get_local_cert_path()
        self.keyfile = agent_ssl_cert.local_key_path()
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
            '127.0.0.1', 0, app, server_class=server_class)
        self.url = '{proto}://localhost:{port}'.format(
            proto='https' if self._ssl else 'http',
            port=self._server.server_port,
        )

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
MIIEyTCCArGgAwIBAgIJAOYXBqHHGL1fMA0GCSqGSIb3DQEBCwUAMBQxEjAQBgNV
BAMMCTEyNy4wLjAuMTAeFw0yMDAzMjUwMDQwMDVaFw0yMTAzMjUwMDQwMDVaMBQx
EjAQBgNVBAMMCTEyNy4wLjAuMTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoC
ggIBANYwTut+k3OyzArW7AljI1Z8ApBDh0uclFEMfn8NRZtCzxU9S6t60G1y8xt4
Elm1mv8ky37Ji/hucZC1W2isqm4eYoT9rhiWeycU0WoFY0r+ch+5NRLMyhSqrTzl
ICurNeCa9g3ec/LMwkv7fTcb3stBJ+H8YH+J3iZeyRjuMh/lSfhtWUd3gY5Xk72I
Ea5+6W0Z7fC035TTvPaAu9saIH+ppwjl6nqEwH3R2XVUtniTBUFaTTMA1y38jgu3
0z8qZWd7fYn+kKkzLgHm/j63J6a3dSh60NdaIlIq0wX1ERkr1UtIftzfHkLkOwKv
5bigEAYxKJ0vBr/+Rp8kMEorGpemdFPdgPbjDr/ykjNnlZboKlu3+eTLBibIdB2r
2+8JjyRgSo1D73R2CIFQxkj4R4dJEj9pj1LcLDGhy6x8LKXCdZ5Y5uenPnxbxP98
FvtWo1eHATuoW+Lnoer+vsmOBwLylaRO86W1ky+1HeR2QRZuy9YnfCu+T2pocr3B
0cKGvABy6g4isXx7hhYBAoQFDJzSjNPQSnkCRpqD+7HBzl88diQjgExy25hqFH8F
snDKKhCjXhkiCTEVPSX4pLp1cZKD2AzFKyTmkWxkEO4zr5cf0vAxDBSSiZN/qWUm
y9NIb1HBAgWdJFz1rsXmhB3qXSfkg0UIdlZXLQi8/nqFB3GNAgMBAAGjHjAcMBoG
A1UdEQQTMBGCCTEyNy4wLjAuMYcEfwAAATANBgkqhkiG9w0BAQsFAAOCAgEAG//5
8zjrMXnR/ocFHwUnv1TN0DQn9rEepg7oZIARPYjqd5/wgXDhEVEOiqohnPhVkICc
8sRHpZ1kbsZG9BQuOgn8vrIdYoKdy1ovCpXovaVn1F/kQz8xuapXXND8zV4oFnvw
bxP9JxnPqtqZLQtaUJR25VtsQU6zhPc9jYzcYH1g+tEff3IxDddVruufBOruSaYM
4Bk+eCe1nQttHk7KQs652xWfXd4FN/BZjmzrVJCFWTgb+f1wJtGlhbnrQRTJFHrh
ursRNyEsgFyc2UcvcOEOIUQWgF05hxdYbBPiYUnqKWduvQr/rxtodkkGOufMfUfM
wgxfupXc9EHe1OS5iAcH9tMODrdJP8UXMMKOZURXineNkOaiosW/AyTAF6AOHp6a
aKkPohA+t8xZr8IGoMS/O/0WJQC9QWB18rVE/95zn1QAcC0WQP84VcFRhRSgQHao
eiBdS15SAnFofBjsuK9dfe6wc5McIsPm0HNN/rJuoCu7rbuu4atogG3RMzwFWQ0j
FtwdXTROil8usOn5h1AVgpGmT+ZPsdufdZzdoUtpauSDlM8rVTHlUOQcWlSF9vkU
LjG57wdRB3mIZDDPrUp5NqHf6q8kEvOHwPYTq1g6H946FvdL67QNhymvayO+0aG7
b2TgtGNlKwd3FS9IMCetxsr4SyXCLPxJuuztFk8=
-----END CERTIFICATE-----"""
    PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
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
W6ymlKLurKPd5YI4Q0y6irWmVMoeaQ==
-----END PRIVATE KEY-----"""

    def __init__(self, base_folder):
        self.temp_folder = base_folder

    def get_local_cert_path(self):
        path = os.path.join(self.temp_folder, 'local.crt')
        with open(path, 'w') as f:
            f.write(_AgentSSLCert.DUMMY_CERT)
        return path

    def local_key_path(self):
        path = os.path.join(self.temp_folder, 'local.key')
        with open(path, 'w') as f:
            f.write(_AgentSSLCert.PRIVATE_KEY)
        return path

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
