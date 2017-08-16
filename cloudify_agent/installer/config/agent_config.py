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
import getpass
import platform

from ntpath import join as nt_join
from functools import wraps, partial
from posixpath import join as posix_join

from cloudify_agent.installer import exceptions
from cloudify_agent.api import utils as agent_utils

from cloudify import ctx
from cloudify import constants
from cloudify import utils as cloudify_utils

from .installer_config import create_runner, get_installer
from .config_errors import raise_missing_attribute, raise_missing_attributes

AGENT_CONFIG_PATH = 'AGENT_CONFIG_PATH'


def create_agent_config_and_installer(func=None,
                                      validate_connection=True,
                                      new_agent_config=False):
    # This allows the decorator to be used with or without arguments
    if not func:
        return partial(
            create_agent_config_and_installer,
            validate_connection=validate_connection,
            new_agent_config=new_agent_config
        )

    @wraps(func)
    def wrapper(*args, **kwargs):
        cloudify_agent = CloudifyAgentConfig()
        cloudify_agent.set_initial_values(new_agent_config, **kwargs)

        if new_agent_config:
            # Set values that need to be inferred from other ones
            cloudify_agent.set_execution_params()
            cloudify_agent.set_default_values()

        runner = create_runner(cloudify_agent, validate_connection)
        cloudify_agent.set_installation_params(runner)

        installer = get_installer(cloudify_agent, runner)
        kwargs['installer'] = installer
        kwargs['cloudify_agent'] = cloudify_agent

        if new_agent_config:
            _update_runtime_properties(cloudify_agent)

        try:
            return func(*args, **kwargs)
        finally:
            if hasattr(runner, 'close'):
                runner.close()

    return wrapper


class CloudifyAgentConfig(dict):
    def set_initial_values(self, new_agent, **kwargs):
        """
        Set the dictionary values in reverse precedence order
        :param new_agent: if set to True, we get additional values from the BS
        context and from node properties. Otherwise, only runtime properties
        and input params are used
        """

        if new_agent:
            self.update(_get_bootstrap_agent_config())  # BS context is 4th
            self.update(_get_node_properties())         # node props are 3rd
        self.update(_get_runtime_properties())      # runtime props are 2nd
        self.update(_get_agent_inputs(kwargs))      # inputs are 1st in order
        self.update(_get_config_from_file())        # config file is 0th

    def set_default_values(self):
        self._set_process_management()
        self._set_name()
        self.setdefault('queue', self['name'])
        self.setdefault('rest_token', cloudify_utils.get_rest_token())
        self.setdefault('rest_tenant', cloudify_utils.get_tenant())
        self.setdefault('rest_host',
                        cloudify_utils.get_manager_rest_service_host())
        self.setdefault('rest_port',
                        cloudify_utils.get_manager_rest_service_port())
        self.setdefault('bypass_maintenance',
                        cloudify_utils.get_is_bypass_maintenance())
        self.setdefault('min_workers', 0)
        self.setdefault('max_workers', 5)
        self.setdefault('disable_requiretty', True)
        self.setdefault('env', {})
        self.setdefault('fabric_env', {})
        self.setdefault('system_python', 'python')

    def _set_process_management(self):
        self.setdefault('process_management', {})
        default_pm_name = 'nssm' if self['windows'] else 'init.d'
        self['process_management'].setdefault('name', default_pm_name)

    def _set_name(self):
        # service_name takes precedence over name (which is deprecated)
        self.setdefault('name', self.get('service_name'))

        if self.get('name'):
            return

        if self['local']:
            workflows_worker = self.get('workflows_worker', False)
            suffix = '_workflows' if workflows_worker else ''
            name = '{0}{1}'.format(ctx.deployment.id, suffix)
        else:
            name = ctx.instance.id
        self['name'] = name

    def set_execution_params(self):
        if 'local' not in self:
            self['local'] = ctx.type == constants.DEPLOYMENT

        if self['local']:
            # If installing an agent locally, we auto-detect which os the agent
            # is dedicated for and we install it with the current user
            self['windows'] = os.name == 'nt'
            self['user'] = getpass.getuser()
            self.setdefault('remote_execution', True)
        else:
            self._set_remote_execution()
            self._set_windows()
            self._set_ip()
            if self['remote_execution']:
                self._set_password()
                self._validate_user()
                self._validate_key_or_password()

    def set_installation_params(self, runner):
        self._set_basedir(runner)
        self.set_config_paths()
        self._set_package_url(runner)

    def _set_remote_execution(self):
        if 'remote_execution' in self:
            return

        install_method = cloudify_utils.internal.get_install_method(
            ctx.node.properties)
        if install_method not in constants.AGENT_INSTALL_METHODS:
            raise exceptions.AgentInstallerConfigurationError(
                'agent_config.install_method must be one of {0}'
                ' but found: {1}'.format(constants.AGENT_INSTALL_METHODS,
                                         install_method))
        remote_execution = (install_method ==
                            constants.AGENT_INSTALL_METHOD_REMOTE)

        self.update({
            'remote_execution': remote_execution,
            'install_method': install_method
        })

    def _set_windows(self):
        if 'windows' in self:
            return

        if ctx.plugin == 'windows_agent_installer':
            # 3.2 Compute node, installing windows
            windows = True
        elif ctx.plugin == 'agent_installer':
            # 3.2 Compute node, installing linux
            windows = False
        else:
            # 3.3 Compute node, determine by new property 'os_family'
            windows = ctx.node.properties['os_family'].lower() == 'windows'

        self['windows'] = windows

    def _set_ip(self):
        # support 'ip' attribute as direct node property or runtime
        # property (as opposed to nested inside the cloudify_agent dict)
        ip = ctx.instance.runtime_properties.get('ip')
        ip = ip or ctx.node.properties.get('ip')
        ip = ip or self.get('ip')

        if not ip and self['remote_execution']:
            # a remote installation requires the ip to connect to.
            raise_missing_attribute('ip')

        if ip:
            self['ip'] = ip

    def _set_password(self):
        # support password as direct node property or runtime
        # property (as opposed to nested inside the cloudify_agent dict)
        password = ctx.instance.runtime_properties.get('password')
        password = password or ctx.node.properties.get('password')
        password = password or self.get('password')

        if not password and self['windows'] and self['remote_execution']:
            # a remote windows installation requires a
            # password to connect to the machine
            raise_missing_attribute('password')

        if password:
            self['password'] = password

    def _validate_user(self):
        # a remote installation requires the username
        # that the agent will run under.
        if not self.get('user'):
            raise_missing_attribute('user')

    def _validate_key_or_password(self):
        """
        A *remote* *linux* installation requires either a password or a key
        file in order to connect to the remote machine
        """
        if self['windows'] or self.get('key') or self.get('password') \
                or not self['remote_execution']:
            return
        raise_missing_attributes('key', 'password')

    def _set_basedir(self, runner):
        if self.get('basedir'):
            return

        if self['local']:
            basedir = agent_utils.get_home_dir(self['user'])
        else:
            if self['windows']:
                # TODO: Get the program files directory from the machine itself
                # instead of hardcoding it an assuming it's in C:\
                basedir = 'C:\\Program Files\\Cloudify Agents'
            elif self['remote_execution']:
                basedir = runner.home_dir(self['user'])
            else:
                basedir = '~{0}'.format(self['user'])
        self['basedir'] = basedir

    def set_config_paths(self):
        join = nt_join if self['windows'] else posix_join

        if not self.get('agent_dir'):
            self['agent_dir'] = join(self['basedir'], self['name'])

        if not self.get('workdir'):
            self['workdir'] = join(self['agent_dir'], 'work')

        if not self.get('envdir'):
            self['envdir'] = join(self['agent_dir'], 'env')

        if not self.get('broker_ssl_cert_path'):
            self['broker_ssl_cert_path'] = \
                cloudify_utils.get_broker_ssl_cert_path()

    def _set_package_url(self, runner):
        if self.get('package_url'):
            return

        agent_package_name = None

        if self['windows']:
            # No distribution difference in windows installation
            agent_package_name = 'cloudify-windows-agent.exe'
        else:
            self._set_agent_distro(runner)
            self._set_agent_distro_codename(runner)

            if 'distro' in self and 'distro_codename' in self:
                agent_package_name = '{0}-{1}-agent.tar.gz'.format(
                    self['distro'], self['distro_codename']
                )

        if agent_package_name:
            file_server_url = agent_utils.get_manager_file_server_url(
                self['rest_host'], self['rest_port']
            )
            self['package_url'] = posix_join(
                file_server_url, 'packages', 'agents', agent_package_name
            )

    def _set_agent_distro(self, runner):
        if self.get('distro'):
            return

        if self['local']:
            self['distro'] = platform.dist()[0].lower()
        elif self['remote_execution']:
            distro = runner.machine_distribution()
            self['distro'] = distro[0].lower()

    def _set_agent_distro_codename(self, runner):
        if 'distro_codename' in self:  # Might be an empty string
            return

        if self['local']:
            self['distro_codename'] = platform.dist()[2].lower()
        elif self['remote_execution']:
            distro = runner.machine_distribution()
            self['distro_codename'] = distro[2].lower()


def _get_config_from_file():
    path = os.environ.get(AGENT_CONFIG_PATH, '/opt/manager/agent_config.json')
    return agent_utils.json_load(path) if path and os.path.exists(path) else {}


def _get_agent_inputs(params):
    """Return the agent config inputs received in the invocation"""

    return _get_agent_config(params, 'operation inputs')


def _get_runtime_properties():
    if ctx.type == constants.NODE_INSTANCE:
        return _get_agent_config(ctx.instance.runtime_properties,
                                 'runtime properties')

    return {}


def _get_node_properties():
    if ctx.type == constants.NODE_INSTANCE:
        return _get_agent_config(
            ctx.node.properties, 'node properties', allow_both_params=True)

    return {}


def _get_bootstrap_agent_config():
    agent_context = ctx.bootstrap_context.cloudify_agent._cloudify_agent or {}
    agent_config = agent_context.copy()
    return _parse_extra_values(agent_config)


def _get_agent_config(params, params_location, allow_both_params=False):
    """Return an agent config dict from `params`"""

    if not allow_both_params:
        if 'agent_config' in params and 'cloudify_agent' in params:
            raise RuntimeError(
                'Both `agent_config` and `cloudify_agent` are set in the '
                '{0}. `cloudify_agent` is deprecated; only '
                '`agent_config` should be used'.format(params_location)
            )

    agent_config = params.get('agent_config') or {}
    cloudify_agent = params.get('cloudify_agent') or {}

    final_dict = agent_config.copy()
    final_dict.update(cloudify_agent)

    return _parse_extra_values(final_dict)


def _parse_extra_values(config):
    extra_dict = config.pop('extra', {})
    config.update(extra_dict)
    return config


def _update_runtime_properties(cloudify_agent):
    """
    Update runtime properties, so that they will be available to future
    operations
    """
    ctx.instance.runtime_properties['cloudify_agent'] = cloudify_agent
    ctx.instance.update()
