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
from cloudify_agent.included_plugins import included_plugins
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
        self.includes_path = os.path.join(
            self.workdir, '{0}-includes'.format(self.name))

        # initd specific configuration
        self.start_on_boot = params.get('start_on_boot', False)

    def configure(self):

        self._logger.debug('Creating includes file: {0}'
                           .format(self.includes_path))
        self._create_includes()
        self._logger.debug('Creating daemon script: {0}'
                           .format(self.script_path))
        self._create_script()
        self._logger.debug('Creating daemon conf file: {0}'
                           .format(self.config_path))
        self._create_config()

        if self.start_on_boot:
            self._logger.info('Creating start-on-boot entry')
            self._create_start_on_boot_entry()

    def delete(self, force=defaults.DAEMON_FORCE_DELETE):

        self._logger.debug('Retrieving daemon stats')
        registered = utils.get_agent_registered(self.name, self._celery)
        if registered:
            if not force:
                raise exceptions.DaemonStillRunningException(self.name)
            self.stop()

        if os.path.exists(self.script_path):
            self._logger.debug('Deleting {0}'.format(self.script_path))
            self._runner.run('sudo rm {0}'.format(self.script_path))
        if os.path.exists(self.config_path):
            self._logger.debug('Deleting {0}'.format(self.config_path))
            self._runner.run('sudo rm {0}'.format(self.config_path))
        if os.path.exists(self.includes_path):
            self._logger.debug('Deleting {0}'.format(self.includes_path))
            self._runner.run('sudo rm {0}'.format(self.includes_path))

    def apply_includes(self):
        with open(self.includes_path, 'w') as f:
            f.write(','.join(self.includes))

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

    def _create_includes(self):
        dir_name = os.path.dirname(self.includes_path)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        open(self.includes_path, 'w').close()

        for plugin in included_plugins:
            self.register(plugin)

    def _create_script(self):
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

    def _create_config(self):
        self._logger.debug('Rendering configuration script from template')
        rendered = utils.render_template_to_file(
            template_path='pm/initd/initd.conf.template',
            queue=self.queue,
            workdir=self.workdir,
            manager_ip=self.manager_ip,
            manager_port=self.manager_port,
            broker_url=self.broker_url,
            user=self.user,
            min_workers=self.min_workers,
            max_workers=self.max_workers,
            includes_path=self.includes_path,
            virtualenv_path=VIRTUALENV,
            extra_env_path=self.extra_env_path,
            name=self.name,
            storage_dir=utils.internal.get_storage_directory(self.user),
            log_level=self.log_level,
            log_file=self.get_logfile(),
            pid_file=self.pid_file,
            cron_respawn=str(self.cron_respawn).lower(),
            enable_cron_script=self.create_enable_cron_script(),
            disable_cron_script=self.create_disable_cron_script()
        )
        self._runner.run('sudo mkdir -p {0}'.format(
            os.path.dirname(self.config_path)))
        self._runner.run('sudo cp {0} {1}'.format(rendered, self.config_path))
        self._runner.run('sudo rm {0}'.format(rendered))

    def _create_start_on_boot_entry(self):

        def _handle_debian():
            self._runner.run('sudo update-rc.d {0} defaults'.format(
                self.service_name))

        def _handle_rpm():
            self._runner.run('sudo /sbin/chkconfig --add {0}'.format(
                self.service_name))
            self._runner.run('sudo /sbin/chkconfig {0} on'.format(
                self.service_name))

        if self._runner.run('which dpkg',
                            exit_on_failure=False).return_code == 0:
            _handle_debian()
            return
        if self._runner.run('which rpm').return_code == 0:
            _handle_rpm()
            return

        raise exceptions.DaemonConfigurationError(
            "Cannot create a start-on-boot entry. Unknown "
            "distribution base. Supported distributions bases are "
            "debian and RPM"
        )


def start_command(daemon):
    return 'sudo service {0} start'.format(daemon.service_name)


def stop_command(daemon):
    return 'sudo service {0} stop'.format(daemon.service_name)


def status_command(daemon):
    return 'sudo service {0} status'.format(daemon.service_name)
