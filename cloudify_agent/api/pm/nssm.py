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

from cloudify import constants

from cloudify_agent import VIRTUALENV
from cloudify_agent.api import defaults
from cloudify_agent.api import exceptions
from cloudify_agent.api import utils
from cloudify_agent.api.pm.base import Daemon


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
        self.configure_script_path = os.path.join(
            self.workdir,
            'configure-service')
        self.app_parameters_path = os.path.join(
            self.workdir,
            'AppParameters'
        )
        self.nssm_path = utils.get_full_resource_path(
            os.path.join('pm', 'nssm', 'nssm.exe'))
        self.agent_service_name = params.get('service_name', 'Cloudify-Agent')
        self.startup_policy = params.get('startup_policy', 'auto')
        self.failure_reset_timeout = params.get('failure_reset_timeout', 60)
        self.failure_restart_delay = params.get('failure_restart_delay', 5000)

    def configure(self):

        params_string = self._create_params_string()
        self.logger.debug('Created params: {0}'.format(params_string))
        env_string = self._create_env_string()
        self.logger.debug('Created environment: {0}'.format(env_string))

        # creating the installation script
        rendered = utils.render_template_to_file(
            template_path='pm/nssm/configure-service.bat.template',
            virtualenv_path=VIRTUALENV,
            agent_service_name=self.agent_service_name,
            params=params_string,
            environment=env_string,
            startup_policy=self.startup_policy,
            failure_reset_timeout=self.failure_reset_timeout,
            failure_restart_delay=self.failure_restart_delay
        )

        self.runner.run('copy {0} {1}'
                        .format(rendered, self.configure_script_path))
        self.logger.debug('Rendered configuration script: {0}'.format(
            self.configure_script_path))
        self.runner.run('del {0}'.format(rendered))

        # saving application parameters for future use
        with open(self.app_parameters_path, 'w') as f:
            f.write(params_string)
        self.logger.debug('Created AppParameters file: {0}'
                          .format(self.app_parameters_path))

        # run the configuration script
        self.logger.info('Running configuration script')
        self.runner.run(self.configure_script_path)
        self.logger.debug('Successfuly executed configuration script')

    def update_includes(self, tasks):
        self.logger.debug('Updating includes configuration '
                          'with new tasks: {0}'.format(tasks))
        with open(self.app_parameters_path) as f:
            app_parameters = f.read()
        includes = app_parameters.split('--include=')[1].split()[0]
        new_includes = '{0},{1}'.format(includes, tasks)

        new_app_parameters = app_parameters.replace(includes, new_includes)

        self.logger.debug('Setting new parameters for {0}: {0}'.format(
            new_app_parameters))
        self.runner.run('{0} set {1} AppParameters {1}'
                        .format(self.nssm_path, self.agent_service_name,
                                new_app_parameters))

        # Write new AppParameters
        with open(name=self.app_parameters_path, mode='w') as f:
            f.write(app_parameters)

    def delete(self, force=defaults.DAEMON_FORCE_DELETE):
        stats = utils.get_agent_stats(self.name, self.celery)
        if stats:
            raise exceptions.DaemonStillRunningException(self.name)

        self.logger.info('Removing {0} service'.format(
            self.agent_service_name))
        self.runner.run('{0} remove {1} confirm'.format(
            self.nssm_path,
            self.agent_service_name))

        self.logger.info('Deleting files...')
        if os.path.exists(self.configure_script_path):
            self.runner.run('del {0}'.format(self.configure_script_path))
        if os.path.exists(self.app_parameters_path):
            self.runner.run('del {0}'.format(self.app_parameters_path))
        self.logger.info('Deleted successfully')

    def start_command(self):
        return 'sc start {}'.format(self.agent_service_name)

    def stop_command(self):
        return 'sc stop {}'.format(self.agent_service_name)

    def _create_params_string(self):
        from cloudify_agent import operations
        return '--broker={0} ' \
               '--events ' \
               '--app=cloudify_agent.app.app ' \
               '-Q {1} ' \
               '-n celery.{1} ' \
               '--autoscale={2},{3} ' \
               '--include={4} '\
            .format(self.broker_url,
                    self.queue,
                    self.min_workers,
                    self.max_workers,
                    operations.CLOUDIFY_AGENT_BUILT_IN_TASK_MODULES)

    def _create_env_string(self):
        environment = {
            constants.MANAGER_IP_KEY: self.manager_ip,
            constants.MANAGER_FILE_SERVER_BLUEPRINTS_ROOT_URL_KEY:
            'http://{0}:53229/blueprints'.format(self.manager_ip),
            constants.MANAGER_FILE_SERVER_URL_KEY:
            'http://{0}:53229'.format(self.manager_ip),
            constants.MANAGER_REST_PORT_KEY: self.manager_port
        }

        # convert the custom environment file to a dictionary
        # file should be a callable batch file in the form of multiple
        # set A=B lines (comments are allowed as well)
        self.logger.debug('Creating environment string from file: {'
                          '0}'.format(self.extra_env_path))
        if self.extra_env_path and os.path.exists(self.extra_env_path):
            with open(self.extra_env_path) as f:
                content = f.read()
            for line in content.split():
                if line.startswith('rem'):
                    break
                parts = line.split(' ')[1].split('=')
                key = parts[0]
                value = parts[1]
                environment[key] = value

        env_string = ''
        for key, value in environment.iteritems():
            env_string = '{0} {1}={2}' \
                .format(env_string, key, value)
        return env_string.strip()
