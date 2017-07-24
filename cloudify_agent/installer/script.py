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
import jinja2
import uuid
import tempfile
from contextlib import contextmanager
from posixpath import join as url_join

from cloudify import ctx, utils as cloudify_utils
from cloudify.constants import CLOUDIFY_TOKEN_AUTHENTICATION_HEADER

from cloudify.utils import (
    get_manager_file_server_root,
    get_manager_file_server_url,
)
from cloudify_agent.api import utils
from cloudify_agent.installer import AgentInstaller
from cloudify_agent.installer.config.agent_config import \
    create_agent_config_and_installer


class AgentInstallationScriptBuilder(AgentInstaller):

    def __init__(self, cloudify_agent):
        super(AgentInstallationScriptBuilder, self).__init__(cloudify_agent)
        self.custom_env = None
        basedir = self.cloudify_agent['basedir']
        if cloudify_agent['windows']:
            self.install_script_template = 'script/windows.ps1.template'
            self.init_script_template = 'script/windows-download.ps1.template'
            self.install_script_filename = '{0}.ps1'.format(uuid.uuid4())
            self.custom_env_path = '{0}\\custom_agent_env.bat'.format(basedir)
        else:
            self.install_script_template = 'script/linux.sh.template'
            self.init_script_template = 'script/linux-download.sh.template'
            self.install_script_filename = '{0}.sh'.format(uuid.uuid4())
            self.custom_env_path = '{0}/custom_agent_env.sh'.format(basedir)

    def install_script(self):
        """Render the agent installation script.
        :return: Install script content
        :rtype: str
        """
        template = jinja2.Template(
            utils.get_resource(self.install_script_template)
        )
        # Called before creating the agent env to populate all the variables
        local_rest_content = self._get_local_cert_content()
        remote_ssl_cert_path = self._get_remote_ssl_cert_path()
        # Called before rendering the template to populate all the variables
        daemon_env = self._create_agent_env()
        return template.render(
            conf=self.cloudify_agent,
            daemon_env=daemon_env,
            pm_options=self._create_process_management_options(),
            custom_env=self.custom_env,
            custom_env_path=self.custom_env_path,
            file_server_url=cloudify_utils.get_manager_file_server_url(),
            configure_flags=self._configure_flags(),
            ssl_cert_content=local_rest_content,
            ssl_cert_path=remote_ssl_cert_path,
            auth_token_header=CLOUDIFY_TOKEN_AUTHENTICATION_HEADER,
            auth_token_value=ctx.rest_token
        )

    def _get_local_cert_content(self):
        local_cert_path = os.path.expanduser(self._get_local_ssl_cert_path())
        with open(local_cert_path, 'r') as f:
            cert_content = f.read().strip()
        return cert_content

    def create_custom_env_file_on_target(self, environment):
        if not environment:
            return
        self.custom_env = environment

    def _get_script_path_and_url(self):
        """
        Calculate install script's local path and download link
        :return: A tuple with:
        1. Path where the install script resides in the file server
        2. URL where the install script can be downloaded
        :rtype: (str, str)
        """
        file_server_root = get_manager_file_server_root()
        file_server_url = get_manager_file_server_url()

        # Store under cloudify_agent to avoid authentication
        script_relpath = os.path.join('cloudify_agent',
                                      self.install_script_filename)
        script_path = os.path.join(file_server_root, script_relpath)
        script_url = url_join(file_server_url, script_relpath)
        return script_path, script_url

    def install_script_download_link(self):
        """Get agent installation script and write it to file server location.
        :return: A tuple with:
        1. Path where the install script resides in the file server
        2. URL where the install script can be downloaded
        :rtype: (str, str)
        """
        script_path, script_url = self._get_script_path_and_url()
        script_content = self.install_script()
        with open(script_path, 'w') as script_file:
            script_file.write(script_content)

        return script_path, script_url

    def init_script(self):
        """Get install script downloader.

        To avoid passing sensitive information through userdata, a simple
        script that downloads the script that actually installs the agent is
        generated.
        :return: Install script downloader content
        :rtype: str
        """
        _, script_url = self.install_script_download_link()
        template = jinja2.Template(
            utils.get_resource(self.init_script_template)
        )
        return template.render(link=script_url)


@create_agent_config_and_installer(validate_connection=False,
                                   new_agent_config=True)
def _get_script_builder(cloudify_agent, **_):
    return AgentInstallationScriptBuilder(cloudify_agent)


def install_script_download_link(cloudify_agent=None, **_):
    script_builder = _get_script_builder(cloudify_agent=cloudify_agent)
    return script_builder.install_script_download_link()


def init_script(cloudify_agent=None, **_):
    script_builder = _get_script_builder(cloudify_agent=cloudify_agent)
    return script_builder.init_script()


@contextmanager
def install_script_path(cloudify_agent):
    script_builder = AgentInstallationScriptBuilder(cloudify_agent)
    script = script_builder.install_script()
    tempdir = tempfile.mkdtemp()
    script_path = os.path.join(tempdir, script_builder.install_script_filename)
    with open(script_path, 'w') as f:
        f.write(script)

    try:
        yield script_path
    finally:
        os.remove(script_path)
