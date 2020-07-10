import os
import sys

from cloudify_agent.tests.utils import (
    create_agent_package,
    get_requirements_uri,
    get_source_uri,
)

try:
    from configparser import RawConfigParser
except ImportError:
    # py2
    from ConfigParser import RawConfigParser


class AgentPackageGenerator(object):
    def __init__(self, file_server):
        self.initialized = False
        self._fs = file_server

    def _initialize(self):
        config = RawConfigParser()
        config.add_section('install')
        config.set('install', 'cloudify_agent_module', get_source_uri())
        config.set('install', 'requirements_file',
                   get_requirements_uri())
        config.add_section('system')
        config.set('system', 'python_path',
                   os.path.join(getattr(sys, 'real_prefix', sys.prefix),
                                'bin', 'python'))
        package_name = create_agent_package(self._fs.root_path, config)
        self._package_url = '{fs_url}/{package_name}'.format(
            fs_url=self._fs.url, package_name=package_name)
        self._package_path = os.path.join(self._fs.root_path, package_name)
        self.initialized = True

    def get_package_url(self):
        if not self.initialized:
            self._initialize()
        return self._package_url

    def get_package_path(self):
        if not self.initialized:
            self._initialize()
        return self._package_path
