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
        self.custom_env_path = None

    def build(self):
        if self.cloudify_agent['windows']:
            resource = 'script/windows.ps1.template'
        else:
            resource = 'script/linux.sh.template'
        template = jinja2.Template(utils.get_resource(resource))
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
        if self.cloudify_agent['windows']:
            self.custom_env_path = '{0}\\custom_agent_env.bat'.format(
                self.cloudify_agent['basedir'])
        else:
            self.custom_env_path = '{0}/custom_agent_env.sh'.format(
                self.cloudify_agent['basedir'])
        return self.custom_env_path


@create_agent_config_and_installer(validate_connection=False, new_agent=True)
def init_script(cloudify_agent, **_):
    return get_install_script(cloudify_agent=cloudify_agent)


def get_install_script(cloudify_agent):
    """Render the agent installation script.

    :param cloudify_agent: Cloudify agent configuration
    :type cloudify_agent: ?
    :return: Install script downloader content
    :rtype: str

    """
    return AgentInstallationScriptBuilder(cloudify_agent).build()


def get_install_script_download_link(cloudify_agent):
    """Get agent installation script and write it to file server location.

    :param cloudify_agent: Cloudify agent configuration
    :type cloudify_agent: ?
    :return: URL where the install script can be downloaded
    :rtype: str

    """
    file_server_root = get_manager_file_server_root()
    file_server_url = get_manager_file_server_url()

    extension = 'ps1' if cloudify_agent['windows'] else 'sh'
    script_filename = '{}.{}'.format(uuid.uuid4(), extension)
    # Store under cloudify_agent to avoid authentication
    script_relpath = os.path.join('cloudify_agent', script_filename)
    script_path = os.path.join(file_server_root, script_relpath)
    script_url = (
        '{}/{}'.
        format(file_server_url, script_relpath)
    )
    script_content = get_install_script(cloudify_agent)
    with open(script_path, 'w') as script_file:
        script_file.write(script_content)

    # TBD: store script path in runtime properties,
    # so that it can be deleted later

    return script_url


def get_init_script(cloudify_agent):
    """Get install script downloader.

    To avoid passig sensitive information through userdata, a simple script
    that downloads the script that actually installs the agent is generated.

    :param cloudify_agent: Cloudify agent configuration
    :type cloudify_agent: ?
    :return: Install script downloader content
    :rtype: str

    """
    script_url = get_install_script_download_link(cloudify_agent)
    if cloudify_agent['windows']:
        resource = 'script/linux-download.sh.template'
    else:
        resource = 'script/windows-download.ps1.template'
    template = jinja2.Template(utils.get_resource(resource))
    return template.render(link=script_url)
