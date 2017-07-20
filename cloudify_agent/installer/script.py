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

from cloudify_agent.api import utils
from cloudify_agent.installer import AgentInstaller
from cloudify_agent.installer.config.agent_config import \
    create_agent_config_and_installer

from manager_rest.config import instance as config


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


def render_agent_installer_script_download_script():
    """Render a script that downloads the script that will install the agent.

    A script to download the real script is needed, to avoid passing sensitive
    data through user data.

    """
    resource = 'script/linux-download.sh.template'
    template = jinja2.Template(utils.get_resource(resource))

    script_filename = '{}.py'.format(uuid.uuid4())
    script_relpath = os.path.join('cloudify_agent', script_filename)
    script_path = os.path.join(config.file_server_root, script_relpath)
    script_url = (
        '{}/{}'.
        format(config.file_server_url, script_relpath)
    )
    script_content = get_init_script()
    with open(script_path, 'w') as script_file:
        script_file.write(script_content)

    return template.render(link=script_url)


@create_agent_config_and_installer(validate_connection=False, new_agent=True)
def init_script(cloudify_agent, **_):
    return get_init_script(cloudify_agent=cloudify_agent)


def get_init_script(cloudify_agent):
    return AgentInstallationScriptBuilder(cloudify_agent).build()
