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

    def configure(self):
        super(SystemDDaemon, self).configure()
        self._runner.run(self._systemctl_command('enable'))
        self._runner.run('sudo systemctl daemon-reload')

    def _delete(self):
        self._runner.run(self._systemctl_command('disable'))

    def _systemctl_command(self, command):
        return 'sudo systemctl {command} {service}'.format(
            command=command,
            service=self.service_name,
        )

    def stop_command(self):
        return self._systemctl_command('stop')

    def start_command(self):
        if not os.path.isfile(self.script_path):
            raise exceptions.DaemonNotConfiguredError(self.name)
        return self._systemctl_command('start')

    def status_command(self):
        return self._systemctl_command('status')

    def _get_script_path(self):
        return os.path.join(
            self.SCRIPT_DIR,
            '{0}.service'.format(self.service_name)
        )

    def _get_rendered_script(self):
        self._logger.debug('Rendering SystemD script from template')
        return utils.render_template_to_file(
            template_path='pm/systemd/systemd.template',
            virtualenv_path=VIRTUALENV,
            user=self.user,
            queue=self.queue,
            config_path=self.config_path,
            max_workers=self.max_workers,
            name=self.name,
            extra_env_path=self.extra_env_path,
        )

    def _get_rendered_config(self):
        self._logger.debug('Rendering configuration script "{0}" from template'
                           .format(self.config_path))
        return utils.render_template_to_file(
            template_path='pm/systemd/systemd.conf.template',
            workdir=self.workdir,
            rest_host=self.rest_host,
            rest_port=self.rest_port,
            local_rest_cert_file=self.local_rest_cert_file,
            log_level=self.log_level.upper(),
            log_dir=self.log_dir,
            log_max_bytes=self.log_max_bytes,
            log_max_history=self.log_max_history,
            name=self.name,
            executable_temp_path=self.executable_temp_path,
        )
