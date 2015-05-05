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
import time
import logging

from cloudify.utils import LocalCommandRunner
from cloudify_agent.included_plugins import included_plugins
from cloudify_agent.api import utils
from cloudify_agent.api.pm.base import Daemon
from cloudify_agent.api import exceptions
from cloudify_agent.api import errors
from cloudify_agent.api import defaults
from cloudify_agent import VIRTUALENV


class GenericLinuxDaemon(Daemon):

    """
    Implementation for the init.d process management.
    """

    SCRIPT_DIR = '/etc/init.d'
    CONFIG_DIR = '/etc/default'
    PROCESS_MANAGEMENT = 'init.d'

    def __init__(self,
                 logger_level=logging.INFO,
                 logger_format=None,
                 **params):
        super(GenericLinuxDaemon, self).__init__(
            logger_level=logger_level,
            logger_format=logger_format,
            **params)

        # init.d specific configuration
        self.script_path = os.path.join(self.SCRIPT_DIR, self.name)
        self.config_path = os.path.join(self.CONFIG_DIR, self.name)
        self.includes_path = os.path.join(
            self.workdir,
            '{0}-includes'.format(self.name)
        )

    def create(self):
        pass

    def configure(self):

        """
        This method creates the following files:

        1. an init.d script located under /etc/init.d
        2. a configuration file located under /etc/default
        3. an includes file containing a comma separated list of modules
           that will be imported at startup.

        :return: The daemon name.
        :rtype: str

        """

        def _validate(file_path):
            if os.path.exists(file_path):
                raise errors.DaemonError(
                    'Failed configuring daemon {0}: {1} already exists.'
                    .format(self.name, file_path))

        # make sure none of the necessary files exist before we create them
        # currently re-configuring an agent is not supported.

        _validate(self.includes_path)
        _validate(self.script_path)
        _validate(self.config_path)

        self.logger.info('Creating includes file: {0}'
                         .format(self.includes_path))
        self._create_includes()
        self.logger.info('Creating daemon script: {0}'
                         .format(self.script_path))
        self._create_script()
        self.logger.info('Creating daemon conf file: {0}'
                         .format(self.config_path))
        self._create_config()

        if self.start_on_boot:
            self._create_start_on_boot_entry()

    def start(self,
              timeout=defaults.START_TIMEOUT,
              interval=defaults.START_INTERVAL):

        """
        Start the daemon process by running an init.d service.

        :raise DaemonStartupTimeout: in case the agent failed to start in the
        given amount of time.
        :raise DaemonException: in case an error happened during the agent
        startup.
        """

        self.logger.info('Starting...')
        self.runner.sudo(start_command(self))
        end_time = time.time() + timeout
        while time.time() < end_time:
            stats = self._get_worker_stats()
            if stats:
                self.logger.info('Started successfully')
                return
            time.sleep(interval)
        self._verify_no_celery_error()
        raise exceptions.DaemonStartupTimeout(timeout)

    def stop(self,
             timeout=defaults.STOP_TIMEOUT,
             interval=defaults.STOP_INTERVAL):

        """
        Stop the init.d service.

        :raise DaemonShutdownTimeout: in case the agent failed to be stopped
        in the given amount of time.
        :raise DaemonException: in case an error happened during the agent
        shutdown.

        """

        self.logger.info('Stopping...')
        self.runner.sudo(stop_command(self))
        end_time = time.time() + timeout
        while time.time() < end_time:
            stats = self._get_worker_stats()
            if not stats:
                self.logger.info('Stopped successfully')
                return
            time.sleep(interval)
        self._verify_no_celery_error()
        raise exceptions.DaemonShutdownTimeout(timeout)

    def delete(self):

        """
        Deletes all the files created on the create method.

        :raise DaemonStillRunningException:
        in case the daemon process is still running.

        """

        self.logger.info('Deleting...')
        stats = self._get_worker_stats()
        if stats:
            raise exceptions.DaemonStillRunningException(self.name)

        if os.path.exists(self.script_path):
            self.runner.sudo('rm {0}'.format(self.script_path))
        if os.path.exists(self.config_path):
            self.runner.sudo('rm {0}'.format(self.config_path))
        if os.path.exists(self.includes_path):
            self.runner.sudo('rm {0}'.format(self.includes_path))
        self.logger.info('Deleted successfully')

    def register(self, plugin):

        """
        This method inspects the files of a given plugin and adds the
        relevant modules to the includes file. This way, subsequent calls to
        'start' will take the new modules under consideration.

        """

        self.logger.info('Registering {0}'.format(plugin))
        plugin_paths = self._list_plugin_files(plugin)

        with open(self.includes_path) as include_file:
            includes = include_file.read()
        new_includes = '{0},{1}'.format(includes, ','.join(plugin_paths))

        if os.path.exists(self.includes_path):
            os.remove(self.includes_path)

        with open(self.includes_path, 'w') as f:
            f.write(new_includes)
        self.logger.info('Registered {0} successfully'.format(plugin))

    def restart(self,
                start_timeout=defaults.START_TIMEOUT,
                start_interval=defaults.START_INTERVAL,
                stop_timeout=defaults.STOP_TIMEOUT,
                stop_interval=defaults.STOP_INTERVAL):

        """
        Restarts the daemon process by calling 'stop' and 'start'

        :raise DaemonStartupTimeout: in case the agent failed to start in the
        given amount of time.
        :raise DaemonShutdownTimeout: in case the agent failed to be stopped
        in the given amount of time.
        :raise DaemonException: in case an error happened during startup or
        shutdown
        """

        self.stop(timeout=stop_timeout,
                  interval=stop_interval)
        self.start(timeout=start_timeout,
                   interval=start_interval)

    def _list_plugin_files(self, plugin_name):

        """
        Retrieves python files related to the plugin.
        __init__ file are filtered out.

        :param plugin_name: The plugin name.
        :type plugin_name: string

        :return: A list of file paths.
        :rtype: list of str
        """

        module_paths = []
        runner = LocalCommandRunner(self.logger)
        files = runner.run(
            '{0}/bin/pip show -f {1}'
            .format(VIRTUALENV, plugin_name)
        ).output.splitlines()
        for module in files:
            if module.endswith('.py') and '__init__' not in module:
                # the files paths are relative to the
                # package __init__.py file.
                module_paths.append(
                    module.replace('../', '')
                    .replace('/', '.').replace('.py', '').strip())
        return module_paths

    def _create_includes(self):
        with open(self.includes_path, 'w') as f:
            includes = []
            for plugin in included_plugins:
                includes.extend(self._list_plugin_files(plugin))
            paths = ','.join(includes)
            self.logger.debug('Writing includes file with {0}'.format(paths))
            f.write(paths)

    def _create_script(self):
        rendered = utils.render_template_to_file(
            template_path='initd/celeryd.template',
            daemon_name=self.name,
            config_path=self.config_path
        )
        self.runner.sudo('cp {0} {1}'.format(rendered, self.script_path))
        self.runner.sudo('rm {0}'.format(rendered))
        self.runner.sudo('chmod +x {0}'.format(self.script_path))

    def _create_config(self):
        rendered = utils.render_template_to_file(
            template_path='initd/celeryd.conf.template',
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
            extra_env_path=self.extra_env_path
        )

        self.runner.sudo('cp {0} {1}'.format(rendered, self.config_path))
        self.runner.sudo('rm {0}'.format(rendered))

    def _create_start_on_boot_entry(self):

        def _handle_debian():
            self.runner.sudo('update-rc.d {0} defaults'.format(self.name))

        def _handle_rpm():
            self.runner.sudo('/sbin/chkconfig --add {0}'.format(self.name))
            self.runner.sudo('/sbin/chkconfig {0} on'.format(self.name))

        if self.runner.run('which dpkg', exit_on_failure=False).code == 0:
            _handle_debian()
            return
        if self.runner.run('which rpm').code == 0:
            _handle_rpm()
            return
        
        raise errors.DaemonConfigurationError(
            "Cannot create a start-on-boot entry. Unknown "
            "distribution base. Supported distributions bases are "
            "debian and RPM"
        )

    def _verify_no_celery_error(self):
        error_file_path = os.path.join(
            self.workdir,
            'celery_error.out')

        # this means the celery worker had an uncaught
        # exception and it wrote its content
        # to the file above because of our custom exception
        # handler (see app.py)
        if os.path.exists(error_file_path):
            with open(error_file_path) as f:
                error = f.read()
            os.remove(error_file_path)
            raise exceptions.DaemonException(error)

    def _get_worker_stats(self):
        destination = 'celery@{0}'.format(self.queue)
        inspect = self.celery.control.inspect(
            destination=[destination])
        stats = (inspect.stats() or {}).get(destination)
        return stats


def start_command(daemon):

    """
    Specifies the command to run when starting the daemon.

    :param daemon: The daemon instance.
    :type daemon: `cloudify_agent.api.internal.daemon.base.Daemon`

    :return: The command to run.
    :rtype: `str`

    """

    return 'service {0} start'.format(daemon.name)


def stop_command(daemon):

    """
    Specifies the command to run when stopping the daemon.

    :param daemon: The daemon instance.
    :type daemon: `cloudify_agent.api.internal.daemon.base.Daemon`

    :return: The command to run.
    :rtype: `str`

    """

    return 'service {0} stop'.format(daemon.name)
