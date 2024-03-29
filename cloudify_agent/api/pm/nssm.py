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

from cloudify.exceptions import CommandExecutionException

from cloudify_agent import VIRTUALENV
from cloudify_agent.api import defaults
from cloudify_agent.api import exceptions
from cloudify_agent.api import utils
from cloudify_agent.api.pm.base import Daemon


class NonSuckingServiceManagerDaemon(Daemon):

    """
    Implementation for the nssm windows service management.
    Based on the nssm service management. see https://nssm.cc/

    Following are all possible custom key-word arguments
    (in addition to the ones available in the base daemon)

    ``startup_policy``

        Specifies the start type for the service.
        possible values are:

            boot - A device driver that is loaded by the boot loader.
            system - A device driver that is started during kernel
                     initialization
            auto - A service that automatically starts each time the
                   computer is restarted and runs even if no one logs on to
                   the computer.
            demand - A service that must be manually started. This is the
                    default value if start= is not specified.
            disabled - A service that cannot be started. To start a disabled
                       service, change the start type to some other value.

    ``failure_reset_timeout``

        Specifies the length of the period (in seconds) with no failures
        after which the failure count should be reset to 0.

    ``failure_restart_delay``

        Specifies delay time (in milliseconds) for the restart action.
    """

    PROCESS_MANAGEMENT = 'nssm'

    RUNNING_STATES = ['SERVICE_RUNNING', 'SERVICE_STOP_PENDING']

    def __init__(self, logger=None, **params):
        super().__init__(logger=logger, **params)

        self.config_path = os.path.join(
            self.workdir,
            '{0}.conf.ps1'.format(self.name))
        self.nssm_path = utils.get_absolute_resource_path(
            os.path.join('pm', 'nssm', 'nssm.exe'))
        self.startup_policy = params.get('startup_policy', 'auto')
        self.failure_reset_timeout = params.get('failure_reset_timeout', 60)
        self.failure_restart_delay = params.get('failure_restart_delay', 5000)
        self.service_user = params.get('service_user', '')
        self.service_password = params.get('service_password', '')

    def create_script(self):
        pass

    def create_config(self):
        # creating the installation script
        self._logger.info('Rendering configuration script "{0}" from template'
                          .format(self.config_path))
        utils.render_template_to_file(
            template_path='pm/nssm/nssm.conf.template',
            file_path=self.config_path,
            queue=self.queue,
            nssm_path=self.nssm_path,
            log_level=self.log_level.upper(),
            log_dir=self.log_dir,
            log_max_bytes=self.log_max_bytes,
            log_max_history=self.log_max_history,
            workdir=self.workdir,
            agent_dir=self.agent_dir,
            resources_root=self.resources_root,
            user=self.user,
            service_user=self.service_user,
            service_password=self.service_password,
            local_rest_cert_file=self.local_rest_cert_file,
            max_workers=self.max_workers,
            virtualenv_path=VIRTUALENV,
            name=self.name,
            custom_environment=self._create_env_string(),
            executable_temp_path=self.executable_temp_path,
            startup_policy=self.startup_policy,
            failure_reset_timeout=self.failure_reset_timeout,
            failure_restart_delay=self.failure_restart_delay,
            storage_dir=utils.internal.get_storage_directory(self.user),
        )

        self._logger.info('Rendered configuration script: {0}'.format(
            self.config_path))

        # run the configuration script
        self._logger.info('Running configuration script')
        try:
            result = self._runner.run([
                'powershell.exe',
                '-ExecutionPolicy', 'bypass',
                '-File', self.config_path,
            ])
            self._logger.info(result.std_out.strip())
            self._logger.warning(result.std_err.strip())
        except Exception:
            # Log the exception here, then re-raise it. This is done in order
            # to ensure that the full exception message is shown.
            self._logger.exception("Failure encountered while running "
                                   "configuration script")
            raise
        self._logger.info('Successfully executed configuration script')

    def before_self_stop(self):
        if self.startup_policy in ['boot', 'system', 'auto']:
            self._logger.debug('Disabling service: {0}'.format(self.name))
            self._runner.run('sc config {0} start= disabled'.format(self.name))
        super(NonSuckingServiceManagerDaemon, self).before_self_stop()

    def delete(self, force=defaults.DAEMON_FORCE_DELETE):
        try:
            self.stop()
        except Exception as e:
            self._logger.info('Deleting agent: could not stop daemon: %s', e)

        self._logger.info('Removing {0} service'.format(
            self.name))
        self._runner.run('{0} remove {1} confirm'.format(
            self.nssm_path,
            self.name))

        self._logger.debug('Deleting {0}'.format(self.config_path))
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

    def start_command(self):
        if not os.path.isfile(self.config_path):
            raise exceptions.DaemonNotConfiguredError(self.name)
        return ['powershell.exe',
                '& Start-Service -Name {0}'.format(self.name)]

    def stop_command(self):
        return ['powershell.exe',
                '& Stop-Service -Name {0}'.format(self.name)]

    def start(self, *args, **kwargs):
        if self.startup_policy in ['boot', 'system', 'auto']:
            self._logger.debug('Enabling service: {0}'.format(self.name))
            self._runner.run('sc config {0} start= {1}'.format(
                self.name, self.startup_policy))
        try:
            super(NonSuckingServiceManagerDaemon, self).start(*args, **kwargs)
        except CommandExecutionException as e:
            if e.code == 1056:
                self._logger.info('Service already started')
            else:
                raise

    def status(self):
        try:
            cmd = '{0} status {1}'.format(self.nssm_path, self.name)
            # apparently nssm output is encoded in utf16.
            state = self._runner.run(cmd, encoding='utf16').std_out.rstrip()
            self._logger.info(state)
            if state in self.RUNNING_STATES:
                return True
            else:
                return False
        except CommandExecutionException as e:
            self._logger.debug(str(e))
            return False

    def _create_env_string(self):
        env_string = ''
        if self.extra_env:
            env_string = ' '.join(
                f'{key}={value}' for key, value in self.extra_env.items()
            )
        return env_string.rstrip()
