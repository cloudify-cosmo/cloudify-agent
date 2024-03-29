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

import getpass
import os

from ntpath import join as nt_join
from functools import wraps
from posixpath import join as posix_join

from cloudify_agent.installer import exceptions
from cloudify_agent.api import utils as agent_utils
from cloudify_agent.api import defaults

from cloudify import ctx
from cloudify import constants
from cloudify import utils as cloudify_utils
from cloudify.agent_utils import (
    create_agent_record,
    get_agent_rabbitmq_user,
)

from .installer_config import create_runner, get_installer
from .config_errors import raise_missing_attribute, raise_missing_attributes


def create_agent_config_and_installer(
    validate_connection=True,
    new_agent_config=False,
):
    def wrapper(func):
        @wraps(func)
        def inner(*args, **kwargs):
            cloudify_agent = CloudifyAgentConfig()
            cloudify_agent.set_initial_values(new_agent_config, **kwargs)

            if new_agent_config:
                # Set values that need to be inferred from other ones
                cloudify_agent.set_execution_params()
                cloudify_agent.set_default_values()
                user_already_exists = get_agent_rabbitmq_user(cloudify_agent)
                create_agent_record(
                    cloudify_agent,
                    create_rabbitmq_user=not user_already_exists,
                )

            runner = create_runner(cloudify_agent, validate_connection)
            if not runner:
                return
            cloudify_agent.set_installation_params(runner)

            if cloudify_agent.has_installer:
                installer = get_installer(cloudify_agent, runner)
            else:
                installer = None
            kwargs['installer'] = installer
            kwargs['cloudify_agent'] = cloudify_agent

            if new_agent_config:
                update_agent_runtime_properties(cloudify_agent)

            try:
                return func(*args, **kwargs)
            finally:
                if hasattr(runner, 'close'):
                    runner.close()
        return inner
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
            # BS context is 5th (to be deprecated)
            self.update(_get_bootstrap_agent_config())
            # config stored on the mannager is the 4th
            self.update(_get_stored_config())
            self.update(_get_node_properties())         # node props are 3rd
        self.update(_get_runtime_properties())      # runtime props are 2nd
        self.update(_get_agent_inputs(kwargs))      # inputs are 1st in order

    @property
    def is_remote(self):
        return self['install_method'] == constants.AGENT_INSTALL_METHOD_REMOTE

    @property
    def is_provided(self):
        return self['install_method'] == \
            constants.AGENT_INSTALL_METHOD_PROVIDED

    @property
    def is_local(self):
        # default 'local' because during agent upgrade, the old agent might
        # have not had it set
        return self.get('local', False)

    @property
    def is_proxied(self):
        return self.get('proxy') is not None

    @property
    def has_installer(self):
        """
        This is useful when deciding whether to run local/remote commands
        """
        return not self.is_proxied and self.is_remote or self.is_local

    @property
    def is_windows(self):
        return self['windows']

    @property
    def tmpdir(self):
        try:
            return self['env'][cloudify_utils.ENV_CFY_EXEC_TEMPDIR]
        except KeyError:
            return None

    def set_default_values(self):
        self._set_name()
        self.setdefault('network', constants.DEFAULT_NETWORK_NAME)
        self._set_ips_and_certs()
        self._set_tenant()
        # Remove the networks dict as it's no longer needed
        if 'networks' in self:
            self.pop('networks')
        self.setdefault('node_instance_id', ctx.instance.id)
        self.setdefault('queue', self['name'])
        self.setdefault('rest_port',
                        cloudify_utils.get_manager_rest_service_port())
        self.setdefault('bypass_maintenance',
                        cloudify_utils.get_is_bypass_maintenance())
        self.setdefault('min_workers', defaults.MIN_WORKERS)
        self.setdefault('max_workers', defaults.MAX_WORKERS)
        self.setdefault('env', {})
        self.setdefault('fabric_env', {})
        self.setdefault('system_python', 'python')
        self.setdefault('heartbeat', None)
        self.setdefault('version', agent_utils.get_agent_version())
        self.setdefault('log_level', defaults.LOG_LEVEL)
        self.setdefault('log_max_bytes', defaults.LOG_FILE_SIZE)
        self.setdefault('log_max_history', defaults.LOG_BACKUPS)
        # detach agents dont use sudo, so they don't need disable-requiretty
        self.setdefault(
            'disable_requiretty',
            self.get('process_management', {}).get('name') != 'detach'
        )

    def _set_process_management(self, runner):
        self.setdefault('process_management', {})

    def _set_name(self):
        # proxied agents dont have a name/queue of their own
        if self.is_proxied:
            self['name'] = None
            return

        # service_name takes precedence over name (which is deprecated)
        self.setdefault('name', self.get('service_name'))

        if self.get('name'):
            return

        self['name'] = ctx.instance.id

    def _set_ips_and_certs(self):
        network = self['network']
        managers = ctx.get_managers(network=network)

        self['rest_host'] = [manager.networks[network] for manager in managers]
        self['rest_ssl_cert'] = '\n'.join(set(
            manager.ca_cert_content.strip() for manager in
            managers if manager.ca_cert_content
        ))
        # setting fileserver url:
        # using the mgmtworker-local one, not all in the cluster.
        # This is because mgmtworker will write a script
        # that is supposed to be downloaded by the agent installer, and that
        # script will only be served by the local restservice, because other
        # restservices would only have it available after the delay of
        # filesystem replication
        local_manager_hostname = cloudify_utils.get_manager_name()
        local_manager_network_ip = None
        for manager in managers:
            if manager.hostname == local_manager_hostname:
                local_manager_network_ip = manager.networks[network]
                break
        if not local_manager_network_ip:
            raise RuntimeError(
                'No fileserver url for manager {0} on network {1}'
                .format(local_manager_hostname, self['network']))
        self['file_server_url'] = agent_utils.get_manager_file_server_url(
            local_manager_network_ip,
            cloudify_utils.get_manager_rest_service_port(),
            scheme=cloudify_utils.get_manager_file_server_scheme()
        )

    def _set_tenant(self):
        if not self.get('tenant'):
            self['tenant'] = ctx.tenant

    def set_execution_params(self):
        self.setdefault('local', False)
        if self.is_local:
            # If installing an agent locally, we auto-detect which os the agent
            # is dedicated for and we install it with the current user
            self['windows'] = os.name == 'nt'
            self['user'] = getpass.getuser()
            self['install_method'] = 'local'
        else:
            self._set_install_method()
            self._set_windows()
            self._set_ip()
            if self.is_remote:
                self._set_password()
                self._validate_user()
                self._validate_key_or_password()

    def set_installation_params(self, runner):
        self._set_process_management(runner)
        self._set_basedir(runner)
        self.set_config_paths()

    def _set_install_method(self):
        install_method = cloudify_utils.internal.get_install_method(
            ctx.node.properties
        )
        # If the install method wasn't specified, it's remote by default
        self['install_method'] = install_method or 'remote'
        if self['install_method'] not in constants.AGENT_INSTALL_METHODS:
            raise exceptions.AgentInstallerConfigurationError(
                'agent_config.install_method must be one of {0}'
                ' but found: {1}'.format(constants.AGENT_INSTALL_METHODS,
                                         self['install_method']))

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
            windows = \
                ctx.node.properties.get('os_family', '').lower() == 'windows'

        self['windows'] = windows

    def _set_ip(self):
        # support 'ip' attribute as direct node property or runtime
        # property (as opposed to nested inside the cloudify_agent dict)
        ip = ctx.instance.runtime_properties.get('ip')
        ip = ip or ctx.node.properties.get('ip')
        ip = ip or self.get('ip')

        if not ip and self.is_remote:
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

        if not password and self.is_windows and self.is_remote:
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
        if self.is_windows or self.get('key') or self.get('password') \
                or not self.is_remote:
            return
        raise_missing_attributes('key', 'password')

    def _set_basedir(self, runner):
        # if basedir is provided by the user explicitly, just use that
        # otherwise, set install_dir to the default basedir + versioned dir
        if self.get('basedir'):
            self['install_dir'] = self['basedir']
            return
        join = nt_join if self.is_windows else posix_join

        self['basedir'] = None
        self['install_dir'] = join(
            agent_utils.get_agent_basedir(self.is_windows),
            f'agent-{agent_utils.get_agent_version()}'
        )

    def set_config_paths(self):
        # proxied agents don't have a name - don't set paths either
        if self.is_proxied:
            return
        join = nt_join if self.is_windows else posix_join

        if not self.get('envdir'):
            self['envdir'] = join(self['install_dir'], 'env')


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


def _get_stored_config():
    return dict(
        (item.name, item.value) for item in ctx.get_config(scope='agent')
    )


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


def update_agent_runtime_properties(cloudify_agent):
    """
    Update runtime properties, so that they will be available to future
    operations
    """
    items_to_remove = ['rest_tenant', 'rest_token',
                       'broker_user', 'broker_pass']
    items_to_remove = []
    for item in items_to_remove:
        cloudify_agent.pop(item, None)
    ctx.instance.runtime_properties['cloudify_agent'] = cloudify_agent
    ctx.instance.update()
