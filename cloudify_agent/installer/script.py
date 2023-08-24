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

from contextlib import contextmanager
import os
import tempfile
import uuid

import jinja2

from cloudify import ctx
from cloudify.constants import CLOUDIFY_TOKEN_AUTHENTICATION_HEADER

from cloudify_agent.api import utils
from cloudify_agent.installer import AgentInstaller
from cloudify_agent.installer.config.agent_config import \
    create_agent_config_and_installer, update_agent_runtime_properties


LOCAL_CLEANUP_PATHS_KEY = 'local_cleanup_paths'


class AgentInstallationScriptBuilder(AgentInstaller):
    def __init__(self, cloudify_agent):
        super(AgentInstallationScriptBuilder, self).__init__(cloudify_agent)

        if cloudify_agent.is_windows:
            self.install_script_template = 'script/windows.ps1.template'
            self.install_script_filename = '{0}.ps1'.format(uuid.uuid4())
        else:
            self.install_script_template = 'script/linux.sh.template'
            self.install_script_filename = '{0}.sh'.format(uuid.uuid4())
        self.stop_old_agent_template = 'script/stop-agent.py.template'
        self.stop_old_agent_filename = '{0}.py'.format(uuid.uuid4())

    @staticmethod
    def _get_template(template_filename):
        return jinja2.Template(
            utils.get_resource(template_filename),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def install_script_download_link(self, add_ssl_cert=True):
        """Get agent installation script and write it to file server location.
        :return: A tuple with:
        1. Path where the install script resides in the file server
        2. URL where the install script can be downloaded
        :rtype: (str, str)
        """
        script_filename = self.install_script_filename
        script_content = self.install_script(add_ssl_cert=add_ssl_cert)
        return self._get_script_url(script_filename, script_content)

    def _get_script_url(self, script_filename, script_content):
        """Accept filename and content, and write it to the fileserver"""
        with tempfile.NamedTemporaryFile(
            delete=False, mode='w',
            suffix='.ps1' if self.cloudify_agent.is_windows else None,
        ) as f:
            f.write(script_content)
        target_resource = os.path.basename(f.name)
        ctx.upload_deployment_file(
            target_resource,
            f.name,

        )
        self._cleanup_after_installation(target_resource)
        return target_resource

    def install_script(self, add_ssl_cert=True):
        """Get install script downloader.

        To avoid passing sensitive information through userdata, a simple
        script that downloads the script that actually installs the agent is
        generated.
        :return: Install script downloader content
        :rtype: str
        """
        template = self._get_template(self.install_script_template)
        use_sudo = self.cloudify_agent.get('install_with_sudo')
        sudo = 'sudo' if use_sudo else ''

        args_dict = dict(
            process_management=self.cloudify_agent['process_management'],
            sudo=sudo,
            conf=self.cloudify_agent,
            auth_token_header=CLOUDIFY_TOKEN_AUTHENTICATION_HEADER,
            auth_token_value=ctx.rest_token,
            install=not self.cloudify_agent.is_provided,
            configure=True,
            start=True,
            debug_flag='--debug' if self.cloudify_agent.get(
                'log_level', '').lower() == 'debug' else '',
            tenant_name=ctx.tenant_name,
            bypass_maintenance=ctx.bypass_maintenance,
            add_ssl_cert=add_ssl_cert,
        )
        return template.render(**args_dict)

    def _cleanup_after_installation(self, path):
        """Mark path to be deleted after agent installation.

        This simply adds the path to cloudify_agent inside runtime properties,
        so that it can be removed later.
        """
        cleanup = self.cloudify_agent.get(LOCAL_CLEANUP_PATHS_KEY, [])
        cleanup.append(path)
        self.cloudify_agent[LOCAL_CLEANUP_PATHS_KEY] = cleanup
        update_agent_runtime_properties(self.cloudify_agent)

    def stop_old_agent(self, old_agent_name):
        template = self._get_template(self.stop_old_agent_template)
        return template.render(agent_name=old_agent_name)

    def stop_old_agent_script_download_link(self, old_agent_name):
        script_filename = self.stop_old_agent_filename
        script_content = self.stop_old_agent(old_agent_name=old_agent_name)
        return self._get_script_url(script_filename, script_content)


@create_agent_config_and_installer(
    validate_connection=False,
    new_agent_config=True,
)
def _get_script_builder(cloudify_agent, **_):
    return AgentInstallationScriptBuilder(cloudify_agent=cloudify_agent)


def install_script_download_link(cloudify_agent=None, **_):
    script_builder = _get_script_builder(cloudify_agent=cloudify_agent)
    return script_builder.install_script_download_link()


def init_script(cloudify_agent=None, **_):
    # back-compat
    script_builder = _get_script_builder(cloudify_agent=cloudify_agent)
    return script_builder.install_script()


install_script = init_script


def stop_agent_script_download_link(cloudify_agent, old_agent_name, **_):
    script_builder = _get_script_builder(cloudify_agent=cloudify_agent)
    return script_builder.stop_old_agent_script_download_link(old_agent_name)


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


def cleanup_scripts():
    """Remove the files that were scheduled for deletion."""
    cloudify_agent = ctx.instance.runtime_properties.get('cloudify_agent', {})
    paths = cloudify_agent.pop(LOCAL_CLEANUP_PATHS_KEY, [])
    update_agent_runtime_properties(cloudify_agent)
    for path in paths:
        try:
            ctx.delete_deployment_file(path)
        except Exception as e:
            ctx.logger.error('Error cleaning up agent script: %s', e)
