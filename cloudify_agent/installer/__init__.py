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

from cloudify.utils import setup_logger
from cloudify_agent.installer.runners.local_runner import LocalCommandRunner
from cloudify.utils import get_is_bypass_maintenance

from cloudify_agent.shell import env
from cloudify_agent.api import utils, defaults

from cloudify import broker_config


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

    def create_agent(self):
        self.upload_rest_certificate()
        self.logger.info('Creating agent from package')
        self._install_agent_package()
        self.run_daemon_command(
            command='create {0}'
            .format(self._create_process_management_options()),
            execution_env=self._create_agent_env())

    def upload_rest_certificate(self):
        local_cert_path = self._get_local_ssl_cert_path()
        remote_cert_path = self._get_remote_ssl_cert_path()
        self.logger.info(
            'Uploading SSL certificate from {0} to {1}'.format(
                local_cert_path, remote_cert_path
            )
        )
        self.runner.put_file(src=local_cert_path, dst=remote_cert_path)

    def _get_local_ssl_cert_path(self):
        default_path = os.environ[env.CLOUDIFY_LOCAL_REST_CERT_PATH]
        return self.cloudify_agent.setdefault('ssl_cert_path', default_path)

    def _get_remote_ssl_cert_path(self):
        agent_dir = os.path.expanduser(self.cloudify_agent['agent_dir'])
        cert_filename = defaults.AGENT_SSL_CERT_FILENAME
        if self.cloudify_agent['windows']:
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

    def _install_agent_package(self):

        self.logger.info('Downloading Agent Package from {0}'.format(
            self.cloudify_agent['package_url']
        ))
        package_path = self.download(url=self.cloudify_agent['package_url'])
        self.logger.info('Untaring Agent package...')
        self.extract(archive=package_path,
                     destination=self.cloudify_agent['agent_dir'])

        self.run_agent_command('configure {0}'.format(self._configure_flags()))

    def _configure_flags(self):
        flags = ''
        if not self.cloudify_agent['windows']:
            flags = '--relocated-env'
            if self.cloudify_agent.get('disable_requiretty'):
                flags = '{0} --disable-requiretty'.format(flags)
        return flags

    def download(self, url, destination=None):
        local_cert_file = self.cloudify_agent['agent_rest_cert_path']
        local_cert_file = os.path.expanduser(local_cert_file)

        return self.runner.download(
            url,
            output_path=destination,
            certificate_file=local_cert_file)

    def move(self, source, target):
        raise NotImplementedError('Must be implemented by sub-class')

    def extract(self, archive, destination):
        raise NotImplementedError('Must be implemented by sub-class')

    def create_custom_env_file_on_target(self, environment):
        raise NotImplementedError('Must be implemented by sub-class')

    @property
    def runner(self):
        raise NotImplementedError('Must be implemented by sub-class')

    @property
    def cfy_agent_path(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def _create_agent_env(self):
        # Try to get broker credentials from the tenant. If they aren't set
        # get them from the broker_config module
        tenant = self.cloudify_agent.get('rest_tenant', {})
        tenant_name = tenant.get('name', defaults.DEFAULT_TENANT_NAME)
        broker_user = tenant.get('rabbitmq_username',
                                 broker_config.broker_username)
        broker_pass = tenant.get('rabbitmq_password',
                                 broker_config.broker_password)
        broker_vhost = tenant.get('rabbitmq_vhost',
                                  broker_config.broker_vhost)

        execution_env = {
            # mandatory values calculated before the agent
            # is actually created
            env.CLOUDIFY_DAEMON_QUEUE: self.cloudify_agent['queue'],
            env.CLOUDIFY_DAEMON_NAME: self.cloudify_agent['name'],
            env.CLOUDIFY_REST_HOST: self.cloudify_agent['rest_host'],
            env.CLOUDIFY_BROKER_IP: self.cloudify_agent['broker_ip'],

            # Optional broker values
            env.CLOUDIFY_BROKER_USER: broker_user,
            env.CLOUDIFY_BROKER_PASS: broker_pass,
            env.CLOUDIFY_BROKER_VHOST: broker_vhost,
            env.CLOUDIFY_BROKER_SSL_ENABLED: broker_config.broker_ssl_enabled,
            env.CLOUDIFY_BROKER_SSL_CERT_PATH:
                self.cloudify_agent['broker_ssl_cert_path'],

            # these are variables that have default values that will be set
            # by the agent on the remote host if not set here
            env.CLOUDIFY_DAEMON_USER: self.cloudify_agent.get('user'),
            env.CLOUDIFY_REST_PORT: self.cloudify_agent.get('rest_port'),
            env.CLOUDIFY_REST_TOKEN: self.cloudify_agent.get('rest_token'),
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
            env.CLOUDIFY_LOCAL_REST_CERT_PATH:
                self.cloudify_agent['agent_rest_cert_path'],
            env.CLOUDIFY_CLUSTER_NODES: json.dumps(
                self.cloudify_agent.get('cluster', []))
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
            options.append('--{0}={1}'.format(key, value))

        return ' '.join(options)


class WindowsInstallerMixin(AgentInstaller):

    @property
    def cfy_agent_path(self):
        return '"{0}\\Scripts\\cfy-agent"'.format(
            self.cloudify_agent['envdir'])

    def extract(self, archive, destination):
        destination = '{0}\\env'.format(destination.rstrip('\\ '))
        if not archive.endswith('.exe'):
            new_archive = '{0}.exe'.format(archive)
            self.move(archive, new_archive)
            archive = new_archive
        self.logger.debug('Extracting {0} to {1}'
                          .format(archive, destination))
        cmd = '{0} /SILENT /VERYSILENT' \
              ' /SUPPRESSMSGBOXES /DIR="{1}"'.format(archive, destination)
        self.runner.run(cmd)
        return destination


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
        posix = not self.cloudify_agent['windows']
        self.logger.debug('Creating a environment file from {0}'
                          .format(environment))
        return utils.env_to_file(env_variables=environment, posix=posix)

    def move(self, source, target):
        shutil.move(source, target)


class RemoteInstallerMixin(AgentInstaller):

    def create_custom_env_file_on_target(self, environment):
        posix = not self.cloudify_agent['windows']
        env_file = utils.env_to_file(env_variables=environment, posix=posix)
        if env_file:
            return self.runner.put_file(src=env_file)
        else:
            return None

    def move(self, source, target):
        self.runner.move(source, target)

    def _create_cert_dir(self, cert_file):
        """Create the directory containing the manager certificate.

        For cross-platform compatibility, use python to create the directory.
        """

        try:
            self.runner.python(
                'import os',
                'os.makedirs(os.path.dirname(os.path.expanduser(\'{0}\')))'
                .format(cert_file))
        except:
            # an error was thrown - if the directory does exist, we assume
            # it was a "directory already exists" error and continue.
            exists = self.runner.python(
                'import os',
                'os.path.exists(os.path.dirname(os.path.expanduser(\'{0}\')))'
                .format(cert_file))

            if 'True' not in exists:
                raise
