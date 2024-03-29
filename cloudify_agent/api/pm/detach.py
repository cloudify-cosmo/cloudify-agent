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
from cloudify_agent.api.pm.base import CronRespawnDaemonMixin


class DetachedDaemon(CronRespawnDaemonMixin):

    """
    This process management is not really a full process management. It
    merely runs the worker command in detached mode and uses crontab for
    re-spawning the daemon on failure. As such, it has the following
    limitations:

        - Daemon does not start on system boot.
        - Crontab re-spawning capabilities are lost after reboot.

    However, the advantage of this kind of daemon is that it does not
    require privileged permissions to execute.
    """

    PROCESS_MANAGEMENT = 'detach'

    def __init__(self, logger=None, **params):
        super().__init__(logger=logger, **params)
        self.script_path = os.path.join(self.workdir, self.name)
        self.config_path = os.path.join(self.workdir, '{0}.conf'.
                                        format(self.name))
        # put the pidfile in the workdir, and not in /var/run or /run,
        # so that detach doesn't need any sudo/su calls to run
        self.pid_file = os.path.join(self.workdir, '{0}.pid'.format(self.name))

    def start(self, interval=defaults.START_INTERVAL,
              timeout=defaults.START_TIMEOUT,
              delete_amqp_queue=defaults.DELETE_AMQP_QUEUE_BEFORE_START):
        super(DetachedDaemon, self).start(interval, timeout, delete_amqp_queue)

        # add cron job to re-spawn the process
        self._logger.debug('Adding cron JOB')
        if self.cron_respawn:
            self._runner.run(self.create_enable_cron_script())

    def before_self_stop(self):
        self._logger.debug('Removing cron JOB')
        if self.cron_respawn:
            self._runner.run(self.create_disable_cron_script())
        super(DetachedDaemon, self).before_self_stop()

    def _delete_queue(self, client):
        queue = '{0}_service'.format(self.queue)
        self._logger.info('Deleting amqp agent queue %s', queue)
        try:
            client.channel_method(
                'queue_delete',
                queue=queue,
                if_empty=True,
                wait=True
            )
        except Exception as err:
            self._logger.warning('Error deleting queue'
                                 ' queue %s: %s', queue, err)
        else:
            self._logger.info(
                'AMQP agent queue %s is deleted '
                'successfully', queue)

    def _delete_exchange(self, client):
        self._logger.info('Deleting amqp agent exchange %s', self.queue)
        try:
            client.channel_method(
                'exchange_delete',
                exchange=self.queue,
            )
        except Exception as err:
            self._logger.warning('Error deleting exchange '
                                 '%s: %s', self.queue, err)
        else:
            self._logger.info(
                'AMQP agent exchange %s is deleted '
                'successfully', self.queue)

    def delete_agent_resources(self):
        self._logger.info('Deleting amqp agent resources...')
        client = self._get_client()
        with client:
            self._delete_queue(client)
            self._delete_exchange(client)
        self._logger.info('All amqp agent resources are deleted '
                          'successfully')

    def delete(self, force=defaults.DAEMON_FORCE_DELETE):
        try:
            self.stop()
        except Exception as e:
            self._logger.info('Deleting agent: could not stop daemon: %s', e)

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
            user=self.user,
            max_workers=self.max_workers,
            virtualenv_path=VIRTUALENV,
            workdir=self.workdir,
            pid_file=self.pid_file
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
            local_rest_cert_file=self.local_rest_cert_file,
            log_level=self.log_level.upper(),
            log_dir=self.log_dir,
            log_max_bytes=self.log_max_bytes,
            log_max_history=self.log_max_history,
            extra_env=self.extra_env,
            storage_dir=utils.internal.get_storage_directory(self.user),
            agent_dir=self.agent_dir,
            workdir=self.workdir,
            executable_temp_path=self.executable_temp_path,
            resources_root=self.resources_root,
        )
