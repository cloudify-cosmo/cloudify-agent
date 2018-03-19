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

from cloudify_agent import VIRTUALENV
from cloudify_agent.api import utils, exceptions
from cloudify_agent.api.pm.base import GenericLinuxDaemonMixin


class SystemDDaemon(GenericLinuxDaemonMixin):

    """
    Implementation for the SystemD process management.

    Following are all possible custom key-word arguments
    (in addition to the ones available in the base daemon)

    """

    SCRIPT_DIR = '/usr/lib/systemd/system/'
    CONFIG_DIR = '/etc/sysconfig'
    PROCESS_MANAGEMENT = 'systemd'

    def __init__(self, logger=None, **params):
        self.service_name = 'cloudify-worker-{0}'.format(self.name)
        script_path = os.path.join(
            self.SCRIPT_DIR, '{0}@.service'.format(self.service_name))
        config_path = os.path.join(self.CONFIG_DIR, self.service_name)
        super(SystemDDaemon, self).__init__(
            logger=logger,
            script_path=script_path,
            config_path=config_path,
            **params
        )

    def configure(self):
        super(SystemDDaemon, self).configure()
        self._runner.run('sudo systemctl daemon-reload')

    def start(self, *args, **kwargs):
        self._runner.run(self.start_command())

    def _status(self):
        self._systemctl_command('status')

    def _delete(self):
        self._runner.run(self._systemctl_command('disable'))

    def _systemctl_command(self, command):
        return 'sudo systemctl {command} {service}'.format(
            command=command,
            service=self.service_name
        )

    def stop_command(self):
        return self._systemctl_command('stop')

    def start_command(self):
        if not os.path.isfile(self.script_path):
            raise exceptions.DaemonNotConfiguredError(self.name)
        return self._systemctl_command('start')

    def status_command(self):
        return self._systemctl_command('status')

    def _get_rendered_script(self):
        self._logger.debug('Rendering SystemD script from template')
        return utils.render_template_to_file(
            template_path='pm/systemd/systemd.template',
            virtualenv_path=VIRTUALENV,
            user=self.user,
            queue=self.queue,
            config_path=self.config_path
        )

    def _get_rendered_config(self):
        self._logger.debug('Rendering configuration script "{0}" from template'
                           .format(self.config_path))
        return utils.render_template_to_file(
            template_path='pm/systemd/systemd.conf.template',
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
            cluster_settings_path=self.cluster_settings_path,
            executable_temp_path=self.executable_temp_path,
            heartbeat=self.heartbeat
        )
