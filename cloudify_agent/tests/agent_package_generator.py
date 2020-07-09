import os
import shutil
import sys
import tempfile

from cloudify_agent.tests.utils import (
    create_agent_package,
    FileServer,
    get_requirements_uri,
    get_source_uri,
)

try:
    from configparser import RawConfigParser
except ImportError:
    # py2
    from ConfigParser import RawConfigParser


class AgentPackageGenerator(object):
    def __init__(self, agent_ssl_cert):
        self.initialized = False
        self.agent_ssl_cert = agent_ssl_cert

    def _initialize(self):
        self._resources_dir = tempfile.mkdtemp(
            prefix='file-server-resource-base')
        self._fs = FileServer(self.agent_ssl_cert,
                              root_path=self._resources_dir, ssl=False)
        self._fs.start()
        config = RawConfigParser()
        config.add_section('install')
        config.set('install', 'cloudify_agent_module', get_source_uri())
        config.set('install', 'requirements_file',
                   get_requirements_uri())
        config.add_section('system')
        config.set('system', 'python_path',
                   os.path.join(getattr(sys, 'real_prefix', sys.prefix),
                                'bin', 'python'))
        package_name = create_agent_package(self._resources_dir, config)
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
