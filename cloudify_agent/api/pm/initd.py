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

from cloudify_agent.api import utils
from cloudify_agent.api import exceptions
from cloudify_agent import VIRTUALENV
from cloudify_agent.api import defaults
from cloudify_agent.api.pm.base import CronRespawnDaemon


class GenericLinuxDaemon(CronRespawnDaemon):

    """
    Implementation for the init.d process management.

    Following are all possible custom key-word arguments
    (in addition to the ones available in the base daemon)

    ``start_on_boot``

        start this daemon when the system boots.

    """

    SCRIPT_DIR = '/etc/init.d'
    CONFIG_DIR = '/etc/default'
    PROCESS_MANAGEMENT = 'init.d'

    def __init__(self, logger=None, **params):
        super(GenericLinuxDaemon, self).__init__(logger=logger, **params)

        self.service_name = 'celeryd-{0}'.format(self.name)
        self.script_path = os.path.join(self.SCRIPT_DIR, self.service_name)
        self.config_path = os.path.join(self.CONFIG_DIR, self.service_name)

        # initd specific configuration
        self.start_on_boot = str(params.get(
            'start_on_boot', 'true')).lower() == 'true'
        self._start_on_boot_handler = _StartOnBootHandler(self.service_name,
                                                          self._runner)

    def configure(self):
        super(GenericLinuxDaemon, self).configure()
        if self.start_on_boot:
            self._logger.info('Creating start-on-boot entry')
            self._start_on_boot_handler.create()

    def delete(self, force=defaults.DAEMON_FORCE_DELETE):
        if self._is_agent_registered():
            if not force:
                raise exceptions.DaemonStillRunningException(self.name)
            self.stop()

        if self.start_on_boot:
            self._logger.info('Deleting start-on-boot entry')
            self._start_on_boot_handler.delete()

        if os.path.exists(self.script_path):
            self._logger.debug('Deleting {0}'.format(self.script_path))
            self._runner.run('sudo rm {0}'.format(self.script_path))
        if os.path.exists(self.config_path):
            self._logger.debug('Deleting {0}'.format(self.config_path))
            self._runner.run('sudo rm {0}'.format(self.config_path))

    def before_self_stop(self):
        if self.start_on_boot:
            self._logger.info('Deleting start-on-boot entry')
            self._start_on_boot_handler.delete()

    def stop_command(self):
        return stop_command(self)

    def start_command(self):
        if not os.path.isfile(self.script_path):
            raise exceptions.DaemonNotConfiguredError(self.name)
        return start_command(self)

    def status_command(self):
        return status_command(self)

    def status(self):
        try:
            self._runner.run(self.status_command())
            return True
        except CommandExecutionException as e:
            self._logger.debug(str(e))
            return False

    def create_script(self):
        self._logger.debug('Rendering init.d script from template')
        rendered = utils.render_template_to_file(
            template_path='pm/initd/initd.template',
            daemon_name=self.name,
            config_path=self.config_path
        )
        self._runner.run('sudo mkdir -p {0}'.format(
            os.path.dirname(self.script_path)))
        self._runner.run('sudo cp {0} {1}'.format(rendered, self.script_path))
        self._runner.run('sudo rm {0}'.format(rendered))
        self._runner.run('sudo chmod +x {0}'.format(self.script_path))

    def create_config(self):
        self._logger.debug('Rendering configuration script "{0}" from template'
                           .format(self.config_path))
        rendered = utils.render_template_to_file(
            template_path='pm/initd/initd.conf.template',
            queue=self.queue,
            workdir=self.workdir,
            rest_host=self.rest_host,
            rest_port=self.rest_port,
            local_rest_cert_file=self.local_rest_cert_file,
            broker_url=self.broker_url,
            user=self.user,
            min_workers=self.min_workers,
            max_workers=self.max_workers,
            virtualenv_path=VIRTUALENV,
            extra_env_path=self.extra_env_path,
            name=self.name,
            storage_dir=utils.internal.get_storage_directory(self.user),
            log_level=self.log_level,
            log_file=self.get_logfile(),
            pid_file=self.pid_file,
            cron_respawn=str(self.cron_respawn).lower(),
            enable_cron_script=self.create_enable_cron_script(),
            disable_cron_script=self.create_disable_cron_script(),
            cluster_settings_path=self.cluster_settings_path
        )
        self._runner.run('sudo mkdir -p {0}'.format(
            os.path.dirname(self.config_path)))
        self._runner.run('sudo cp {0} {1}'.format(rendered, self.config_path))
        self._runner.run('sudo rm {0}'.format(rendered))


def start_command(daemon):
    return 'sudo service {0} start'.format(daemon.service_name)


def stop_command(daemon):
    return 'sudo service {0} stop'.format(daemon.service_name)


def status_command(daemon):
    return 'sudo service {0} status'.format(daemon.service_name)


class _StartOnBootHandler(object):

    def __init__(self, service_name, runner):
        self._name = service_name
        self._runner = runner
        self._distro = None

    def create(self):
        if self.distro == 'debian':
            commands = ['sudo update-rc.d {0} defaults'.format(self._name)]
        elif self.distro == 'rpm':
            commands = ['sudo /sbin/chkconfig --add {0}'.format(self._name),
                        'sudo /sbin/chkconfig {0} on'.format(self._name)]
        else:
            raise RuntimeError('Illegal state')
        for command in commands:
            self._runner.run(command)

    def delete(self):
        if self.distro == 'debian':
            command = 'sudo update-rc.d -f {0} remove'.format(self._name)
        elif self.distro == 'rpm':
            command = 'sudo /sbin/chkconfig {0} off'.format(self._name)
        else:
            raise RuntimeError('Illegal state')
        self._runner.run(command)

    @property
    def distro(self):
        if not self._distro:
            if self._runner.run('which dpkg',
                                exit_on_failure=False).return_code == 0:
                self._distro = 'debian'
            elif self._runner.run('which rpm',
                                  exit_on_failure=False).return_code == 0:
                self._distro = 'rpm'
            else:
                raise exceptions.DaemonConfigurationError(
                    "Cannot create a start-on-boot entry. Unknown "
                    "distribution base. Supported distributions bases are "
                    "debian and RPM")
        return self._distro
