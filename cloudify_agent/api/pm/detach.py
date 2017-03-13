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
from cloudify_agent.api import utils
from cloudify_agent.api import exceptions
from cloudify_agent.api.pm.base import CronRespawnDaemon


class DetachedDaemon(CronRespawnDaemon):

    """
    This process management is not really a full process management. It
    merely runs the celery command in detached mode and uses crontab for
    re-spawning the daemon on failure. As such, it has the following
    limitations:

        - Daemon does not start on system boot.
        - Crontab re-spawning capabilities are lost after reboot.

    However, the advantage of this kind of daemon is that it does not
    require privileged permissions to execute.
    """

    PROCESS_MANAGEMENT = 'detach'

    def __init__(self, logger=None, **params):
        super(DetachedDaemon, self).__init__(logger, **params)
        self.script_path = os.path.join(self.workdir, self.name)
        self.config_path = os.path.join(self.workdir, '{0}.conf'.
                                        format(self.name))

    def start(self, interval=defaults.START_INTERVAL,
              timeout=defaults.START_TIMEOUT,
              delete_amqp_queue=defaults.DELETE_AMQP_QUEUE_BEFORE_START):
        super(DetachedDaemon, self).start(interval, timeout, delete_amqp_queue)

        # add cron job to re-spawn the process
        self._logger.debug('Adding cron JOB')
        self._runner.run(self.create_enable_cron_script())

    def stop(self, interval=defaults.STOP_INTERVAL,
             timeout=defaults.STOP_TIMEOUT):
        # remove cron job
        self._logger.debug('Removing cron JOB')
        self._runner.run(self.create_disable_cron_script())
        super(DetachedDaemon, self).stop(interval, timeout)

    def delete(self, force=defaults.DAEMON_FORCE_DELETE):
        if self._is_agent_registered():
            if not force:
                raise exceptions.DaemonStillRunningException(self.name)
            self.stop()

        if os.path.exists(self.pid_file):
            self._logger.debug('Removing {0}'.format(self.pid_file))
            os.remove(self.pid_file)
        if os.path.exists(self.config_path):
            self._logger.debug('Removing {0}'.format(self.config_path))
            os.remove(self.config_path)
        if os.path.exists(self.script_path):
            self._logger.debug('Removing {0}'.format(self.script_path))
            os.remove(self.script_path)

    def start_command(self):
        if not os.path.isfile(self.script_path):
            raise exceptions.DaemonNotConfiguredError(self.name)
        return self.script_path

    def stop_command(self):
        with open(self.pid_file) as f:
            pid = f.read()
        return 'kill -9 {0}'.format(pid)

    def status_command(self):
        with open(self.pid_file) as f:
            pid = f.read()
        return 'kill -s 0 {0}'.format(pid)

    def status(self):
        try:
            if not os.path.exists(self.pid_file):
                return False
            response = self._runner.run(self.status_command())
            self._logger.info(response.std_out)
            return True
        except CommandExecutionException as e:
            self._logger.debug(str(e))
            return False

    def create_script(self):
        self._logger.debug('Rendering detached script from template')
        rendered = utils.render_template_to_file(
            template_path='pm/detach/detach.template',
            config_path=self.config_path,
            queue=self.queue,
            name=self.name,
            log_level=self.log_level,
            log_file=self.get_logfile(),
            pid_file=self.pid_file,
            broker_url=self.broker_url,
            min_workers=self.min_workers,
            max_workers=self.max_workers,
            virtualenv_path=VIRTUALENV,
            workdir=self.workdir
        )

        # no sudo needed, yey!
        self._runner.run('cp {0} {1}'.format(rendered, self.script_path))
        self._runner.run('rm {0}'.format(rendered))
        self._runner.run('chmod +x {0}'.format(self.script_path))

    def create_config(self):
        self._logger.debug('Rendering configuration script "{0}" from template'
                           .format(self.config_path))
        utils.render_template_to_file(
            template_path='pm/detach/detach.conf.template',
            file_path=self.config_path,
            user=self.user,
            name=self.name,
            broker_url=self.broker_url,
            rest_host=self.rest_host,
            rest_port=self.rest_port,
            local_rest_cert_file=self.local_rest_cert_file,
            extra_env_path=self.extra_env_path,
            storage_dir=utils.internal.get_storage_directory(self.user),
            workdir=self.workdir,
            cluster_settings_path=self.cluster_settings_path
        )
