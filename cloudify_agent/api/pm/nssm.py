#########
# Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
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
import logging

from cloudify_agent import VIRTUALENV
from cloudify_agent.api import defaults
from cloudify_agent.api import exceptions
from cloudify_agent.api import utils
from cloudify_agent.api.pm.base import Daemon
from cloudify_agent.api import errors
from cloudify_agent.included_plugins import included_plugins


###########################################
# Based on the nssm service management.
# see https://nssm.cc/
###########################################

class NonSuckingServiceManagerDaemon(Daemon):

    """
    Implementation for the nssm windows service management.
    """

    PROCESS_MANAGEMENT = 'nssm'

    def __init__(self,
                 logger_level=logging.INFO,
                 logger_format=None,
                 **params):
        super(NonSuckingServiceManagerDaemon, self).__init__(
            logger_level,
            logger_format,
            **params)

        # nssm specific configuration
        self.config_path = os.path.join(
            self.workdir,
            '{0}.conf.bat'.format(self.name))
        self.nssm_path = utils.get_full_resource_path(
            os.path.join('pm', 'nssm', 'nssm.exe'))
        self.startup_policy = params.get('startup_policy', 'auto')
        self.failure_reset_timeout = params.get('failure_reset_timeout', 60)
        self.failure_restart_delay = params.get('failure_restart_delay', 5000)

        self.celery_log_level = params.get('celery_log_level', 'debug')
        self.celery_log_file = os.path.join(self.workdir,
                                            '{0}-celery.log'.format(self.name))
        self.celery_pid_file = os.path.join(self.workdir,
                                            '{0}-celery.pid'.format(self.name))

    def configure(self):

        env_string = self._create_env_string()
        if env_string:
            self.logger.debug('Created extra environment: {0}'
                              .format(env_string))

        if os.path.exists(self.config_path):
            raise errors.DaemonError(
                'Failed configuring daemon {0}: {1} already exists.'
                .format(self.name, self.config_path))

        # creating the installation script
        utils.render_template_to_file(
            template_path='pm/nssm/nssm.conf.template',
            file_path=self.config_path,
            queue=self.queue,
            nssm_path=self.nssm_path,
            celery_log_level=self.celery_log_level,
            celery_log_file=self.celery_log_file,
            celery_pid_file=self.celery_pid_file,
            workdir=self.workdir,
            user=self.user,
            manager_ip=self.manager_ip,
            manager_port=self.manager_port,
            broker_url=self.broker_url,
            min_workers=self.min_workers,
            max_workers=self.max_workers,
            includes=','.join(self.includes),
            virtualenv_path=VIRTUALENV,
            name=self.name,
            storage_dir=utils.get_storage_directory(self.user),
            custom_environment=env_string,
            startup_policy=self.startup_policy,
            failure_reset_timeout=self.failure_reset_timeout,
            failure_restart_delay=self.failure_restart_delay
        )

        self.logger.debug('Rendered configuration script: {0}'.format(
            self.config_path))

        # run the configuration script
        self.logger.info('Running configuration script')
        self.runner.run(self.config_path)
        self.logger.debug('Successfully executed configuration script')

        # register plugins
        for plugin in included_plugins:
            self.logger.info('Registering plugin: {0}'.format(plugin))
            self.register(plugin)

    def set_includes(self):
        self.logger.debug('Setting includes configuration '
                          'with: {0}'.format(self.includes))

        output = self.runner.run('{0} get {1} AppParameters'
                                 .format(self.nssm_path,
                                         self.name)
                                 ).output

        # apparently nssm output is encoded in utf16 without BOM
        # encode to ascii to be able to parse this
        app_parameters = output.decode('utf16').encode('utf-8').rstrip()

        current_includes = app_parameters.split('--include=')[1].split()[0]

        new_app_parameters = app_parameters.replace(
            current_includes,
            ','.join(self.includes))

        self.logger.debug('Setting new parameters for {0}: {1}'.format(
            self.name, app_parameters))
        self.runner.run('{0} set {1} AppParameters {2}'
                        .format(self.nssm_path, self.name,
                                new_app_parameters))

    def delete(self, force=defaults.DAEMON_FORCE_DELETE):
        stats = utils.get_agent_stats(self.name, self.celery)
        if stats:
            if not force:
                raise exceptions.DaemonStillRunningException(self.name)
            self.logger.debug(
                'Requested to delete daemon with force, '
                'stopping daemon {0} before deletion.'.format(self.name))
            self.stop()

        self.logger.info('Removing {0} service'.format(
            self.name))
        self.runner.run('{0} remove {1} confirm'.format(
            self.nssm_path,
            self.name))

        self.logger.info('Deleting files...')
        if os.path.exists(self.config_path):
            os.remove(self.config_path)
        self.logger.info('Deleted successfully')

    def start_command(self):
        return 'sc start {0}'.format(self.name)

    def stop_command(self):
        return 'sc stop {0}'.format(self.name)

    def _create_env_string(self):
        # convert the custom environment file to a dictionary
        # file should be a callable batch file in the form of multiple
        # set A=B lines (comments are allowed as well)
        env_string = ''
        self.logger.debug('Creating environment string from file: {'
                          '0}'.format(self.extra_env_path))
        if self.extra_env_path and os.path.exists(self.extra_env_path):
            with open(self.extra_env_path) as f:
                content = f.read()
            for line in content.splitlines():
                if line.startswith('set'):
                    parts = line.split(' ')[1].split('=')
                    key = parts[0]
                    value = parts[1]
                    env_string = '{0} {1}={2}'.format(env_string, key, value)
        return env_string.rstrip()
