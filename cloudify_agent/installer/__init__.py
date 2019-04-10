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
import json
import shutil
import ntpath
import copy
import base64

try:
    # Python 3.3+
    from shlex import quote
except ImportError:
    # Python 2.7
    from pipes import quote

from cloudify_agent.installer.runners.local_runner import LocalCommandRunner
from cloudify.utils import (get_tenant,
                            setup_logger,
                            get_rest_token,
                            get_is_bypass_maintenance)

from cloudify_agent.shell import env
from cloudify_agent.api import utils, defaults

from cloudify import broker_config
from cloudify import ctx


class AgentInstaller(object):

    def __init__(self,
                 cloudify_agent,
                 logger=None):
        self.cloudify_agent = cloudify_agent
        self.logger = logger or setup_logger(self.__class__.__name__)

    def run_agent_command(self, command, execution_env=None):
        if execution_env is None:
            execution_env = {}
        response = self.runner.run(
            command='{0} {1}'.format(self.cfy_agent_path, command),
            execution_env=execution_env)
        output = response.std_out
        if output:
            for line in output.splitlines():
                self.logger.info(line)
        return response

    def run_daemon_command(self, command,
                           execution_env=None):
        return self.run_agent_command(
            command='daemons {0} --name={1}'
            .format(command, self.cloudify_agent['name']),
            execution_env=execution_env)

    def _get_local_ssl_cert_paths(self):
        if self.cloudify_agent.get('ssl_cert_path'):
            return [self.cloudify_agent['ssl_cert_path']]
        else:
            return [
                os.environ[env.CLOUDIFY_LOCAL_REST_CERT_PATH],
                os.environ[env.CLOUDIFY_BROKER_SSL_CERT_PATH],
            ]

    def _get_remote_ssl_cert_path(self):
        agent_dir = os.path.expanduser(self.cloudify_agent['agent_dir'])
        cert_filename = defaults.AGENT_SSL_CERT_FILENAME
        if self.cloudify_agent.is_windows:
            path_join = ntpath.join
            ssl_target_dir = defaults.SSL_CERTS_TARGET_DIR.replace('/', '\\')
        else:
            path_join = os.path.join
            ssl_target_dir = defaults.SSL_CERTS_TARGET_DIR

        path = path_join(agent_dir, ssl_target_dir, cert_filename)
        self.cloudify_agent['agent_rest_cert_path'] = path
        self.cloudify_agent['broker_ssl_cert_path'] = path
        return path

    def configure_agent(self):
        self.run_daemon_command('configure')

    def start_agent(self):
        self.run_daemon_command('start')

    def stop_agent(self):
        self.run_daemon_command('stop')

    def delete_agent(self):
        self.run_daemon_command('delete')
        self.runner.delete(self.cloudify_agent['agent_dir'])

    def restart_agent(self):
        self.run_daemon_command('restart')

    def _configure_flags(self):
        flags = ''
        if not self.cloudify_agent.is_windows:
            flags = '--relocated-env'
            if self.cloudify_agent.get('disable_requiretty'):
                flags = '{0} --disable-requiretty'.format(flags)
        return flags

    def create_custom_env_file_on_target(self, environment):
        raise NotImplementedError('Must be implemented by sub-class')

    @property
    def runner(self):
        raise NotImplementedError('Must be implemented by sub-class')

    @property
    def cfy_agent_path(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def _create_agent_env(self):
        tenant = get_tenant()
        tenant_name = tenant.get('name', defaults.DEFAULT_TENANT_NAME)
        tenant_user = tenant.get('rabbitmq_username',
                                 broker_config.broker_username)
        tenant_pass = tenant.get('rabbitmq_password',
                                 broker_config.broker_password)
        broker_vhost = tenant.get('rabbitmq_vhost',
                                  broker_config.broker_vhost)
        # Get the agent's broker credentials
        broker_user = self.cloudify_agent.get('broker_user', tenant_user)
        broker_pass = self.cloudify_agent.get('broker_pass', tenant_pass)

        manager_ip = self.cloudify_agent.get_manager_ip()
        network = self.cloudify_agent.get('network')
        execution_env = {
            # mandatory values calculated before the agent
            # is actually created
            env.CLOUDIFY_DAEMON_QUEUE: self.cloudify_agent['queue'],
            env.CLOUDIFY_DAEMON_NAME: self.cloudify_agent['name'],
            env.CLOUDIFY_REST_HOST: manager_ip,
            env.CLOUDIFY_BROKER_IP: ','.join(
                broker.networks[network] for broker in
                ctx.get_brokers(network=network)
            ),

            # Optional broker values
            env.CLOUDIFY_BROKER_USER: broker_user,
            env.CLOUDIFY_BROKER_PASS: broker_pass,
            env.CLOUDIFY_BROKER_VHOST: broker_vhost,
            env.CLOUDIFY_BROKER_SSL_ENABLED: broker_config.broker_ssl_enabled,
            env.CLOUDIFY_BROKER_SSL_CERT_PATH: (
                self.cloudify_agent['broker_ssl_cert_path']
            ),
            env.CLOUDIFY_HEARTBEAT: (
                self.cloudify_agent.get('heartbeat')
            ),

            # these are variables that have default values that will be set
            # by the agent on the remote host if not set here
            env.CLOUDIFY_DAEMON_USER: self.cloudify_agent.get('user'),
            env.CLOUDIFY_REST_PORT: self.cloudify_agent.get('rest_port'),
            env.CLOUDIFY_REST_TOKEN: get_rest_token(),
            env.CLOUDIFY_REST_TENANT: tenant_name,
            env.CLOUDIFY_DAEMON_MAX_WORKERS: self.cloudify_agent.get(
                'max_workers'),
            env.CLOUDIFY_DAEMON_MIN_WORKERS: self.cloudify_agent.get(
                'min_workers'),
            env.CLOUDIFY_DAEMON_PROCESS_MANAGEMENT:
            self.cloudify_agent['process_management']['name'],
            env.CLOUDIFY_DAEMON_WORKDIR: self.cloudify_agent['workdir'],
            env.CLOUDIFY_DAEMON_EXTRA_ENV:
            self.create_custom_env_file_on_target(
                self.cloudify_agent.get('env', {})),
            env.CLOUDIFY_BYPASS_MAINTENANCE_MODE: get_is_bypass_maintenance(),
            env.CLOUDIFY_LOCAL_REST_CERT_PATH: (
                self.cloudify_agent['agent_rest_cert_path']
            ),
            env.CLOUDIFY_CLUSTER_NODES: base64.b64encode(json.dumps(
                self.cloudify_agent.get('cluster', []))),
            env.CLOUDIFY_NETWORK_NAME: network
        }

        execution_env = utils.purge_none_values(execution_env)
        execution_env = utils.stringify_values(execution_env)

        self.logger.debug('Cloudify Agent will be created using the following '
                          'environment: {0}'.format(execution_env))

        return execution_env

    def _create_process_management_options(self):
        options = []
        process_management = copy.deepcopy(self.cloudify_agent[
            'process_management'])

        # remove the name key because it is
        # actually passed separately via an
        # environment variable
        process_management.pop('name')
        for key, value in process_management.iteritems():
            options.append("--{0}={1}".format(key, quote(value)))

        return ' '.join(options)


class WindowsInstallerMixin(AgentInstaller):

    @property
    def cfy_agent_path(self):
        return '"{0}\\Scripts\\cfy-agent"'.format(
            self.cloudify_agent['envdir'])


class LinuxInstallerMixin(AgentInstaller):

    @property
    def cfy_agent_path(self):
        return '"{0}/bin/python" "{0}/bin/cfy-agent"'.format(
            self.cloudify_agent['envdir'])


class LocalInstallerMixin(AgentInstaller):

    @property
    def runner(self):
        return LocalCommandRunner(logger=self.logger)

    def delete_agent(self):
        self.run_daemon_command('delete')
        shutil.rmtree(self.cloudify_agent['agent_dir'])

    def create_custom_env_file_on_target(self, environment):
        posix = not self.cloudify_agent.is_windows
        self.logger.debug('Creating a environment file from {0}'
                          .format(environment))
        return utils.env_to_file(env_variables=environment, posix=posix)


class RemoteInstallerMixin(AgentInstaller):

    def create_custom_env_file_on_target(self, environment):
        posix = not self.cloudify_agent.is_windows
        env_file = utils.env_to_file(env_variables=environment, posix=posix)
        if env_file:
            return self.runner.put_file(src=env_file)
        else:
            return None
