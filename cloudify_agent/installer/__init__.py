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

import ntpath
import os
import shutil

from cloudify_agent.installer.runners.local_runner import LocalCommandRunner
from cloudify.utils import setup_logger

from cloudify_agent.shell import env
from cloudify_agent.api import defaults


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
            flags = '--fix-shebangs'
        return flags

    @property
    def runner(self):
        raise NotImplementedError('Must be implemented by sub-class')

    @property
    def cfy_agent_path(self):
        raise NotImplementedError('Must be implemented by sub-class')


class WindowsInstallerMixin(AgentInstaller):

    @property
    def cfy_agent_path(self):
        script_path = ntpath.join(
            self.cloudify_agent['install_dir'],
            'Scripts',
            "cfy-agent.exe",
        )
        return f'"{script_path}"'


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
