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
from cloudify_agent.included_plugins import included_plugins
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
        self.includes_path = os.path.join(
            self.workdir, '{0}-includes'.format(self.name))

    def start(self, interval=defaults.START_INTERVAL,
              timeout=defaults.START_TIMEOUT,
              delete_amqp_queue=defaults.DELETE_AMQP_QUEUE_BEFORE_START):
        super(DetachedDaemon, self).start(interval, timeout, delete_amqp_queue)

        # add cron job to re-spawn the process
        self._logger.debug('Adding cron JOB')
        self._runner.run(self.create_enable_cron_script())

    def stop(self, interval=defaults.STOP_INTERVAL,
             timeout=defaults.STOP_TIMEOUT):
        super(DetachedDaemon, self).stop(interval, timeout)

        # remove cron job
        self._logger.debug('Removing cron JOB')
        self._runner.run(self.create_disable_cron_script())

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

        # Add the celery config
        self._logger.info('Deploying SSL cert (if defined).')
        self._create_ssl_cert()
        self._logger.info('Deploying celery configuration.')
        self._create_celery_conf()

    def delete(self, force=defaults.DAEMON_FORCE_DELETE):

        self._logger.debug('Retrieving daemon registered tasks')
        registered = utils.get_agent_registered(self.name, self._celery)
        if registered:
            if not force:
                raise exceptions.DaemonStillRunningException(self.name)
            self.stop()

        if os.path.exists(self.pid_file):
            self._logger.debug('Removing {0}'.format(self.pid_file))
            os.remove(self.pid_file)
        if os.path.exists(self.includes_path):
            self._logger.debug('Removing {0}'.format(self.includes_path))
            os.remove(self.includes_path)
        if os.path.exists(self.config_path):
            self._logger.debug('Removing {0}'.format(self.config_path))
            os.remove(self.config_path)
        if os.path.exists(self.script_path):
            self._logger.debug('Removing {0}'.format(self.script_path))
            os.remove(self.script_path)

    def apply_includes(self):
        with open(self.includes_path, 'w') as f:
            f.write(','.join(self.includes))

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

    def _create_includes(self):
        dir_name = os.path.dirname(self.includes_path)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        open(self.includes_path, 'w').close()

        for plugin in included_plugins:
            self.register(plugin)

    def _create_script(self):
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
            includes_path=self.includes_path,
            virtualenv_path=VIRTUALENV
        )

        # no sudo needed, yey!
        self._runner.run('cp {0} {1}'.format(rendered, self.script_path))
        self._runner.run('rm {0}'.format(rendered))
        self._runner.run('chmod +x {0}'.format(self.script_path))

    def _create_config(self):
        self._logger.debug('Rendering configuration script from template')
        utils.render_template_to_file(
            template_path='pm/detach/detach.conf.template',
            file_path=self.config_path,
            user=self.user,
            name=self.name,
            broker_url=self.broker_url,
            manager_ip=self.manager_ip,
            manager_port=self.manager_port,
            manager_protocol=self.manager_protocol,
            security_enabled=self.security_enabled,
            manager_username=self.manager_username,
            manager_password=self.manager_password,
            verify_manager_certificate=self.verify_manager_certificate,
            local_manager_cert_path=self.local_manager_cert_path,
            extra_env_path=self.extra_env_path,
            storage_dir=utils.internal.get_storage_directory(self.user),
            workdir=self.workdir,
        )
