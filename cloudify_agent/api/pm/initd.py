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

from cloudify_agent.api import utils
from cloudify_agent.api.pm.base import Daemon
from cloudify_agent.api import exceptions
from cloudify_agent.api import errors
from cloudify_agent import VIRTUALENV
from cloudify_agent.api import defaults
from cloudify_agent import operations


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
            self.workdir, '{0}-includes'.format(self.name))
        self.start_on_boot = params.get('start_on_boot', False)

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

        self.logger.debug('Creating includes file: {0}'
                          .format(self.includes_path))
        self._create_includes()
        self.logger.debug('Creating daemon script: {0}'
                          .format(self.script_path))
        self._create_script()
        self.logger.debug('Creating daemon conf file: {0}'
                          .format(self.config_path))
        self._create_config()

        if self.start_on_boot:
            self.logger.info('Creating start-on-boot entry')
            self._create_start_on_boot_entry()

    def delete(self, force=defaults.DAEMON_FORCE_DELETE):

        """
        Deletes all the files created on the create method.

        :raise DaemonStillRunningException:
        in case the daemon process is still running.

        """

        stats = utils.get_agent_stats(self.name, self.celery)
        if stats:
            if not force:
                raise exceptions.DaemonStillRunningException(self.name)
            self.logger.debug(
                'Requested to delete daemon with force, '
                'stopping daemon {0} before deletion.'.format(self.name))
            self.stop()

        if os.path.exists(self.script_path):
            self.logger.debug('Deleting {0}'.format(self.script_path))
            self.runner.run('sudo rm {0}'.format(self.script_path))
        if os.path.exists(self.config_path):
            self.logger.debug('Deleting {0}'.format(self.config_path))
            self.runner.run('sudo rm {0}'.format(self.config_path))
        if os.path.exists(self.includes_path):
            self.logger.debug('Deleting {0}'.format(self.includes_path))
            self.runner.run('sudo rm {0}'.format(self.includes_path))

    def update_includes(self, tasks):
        self.logger.debug('Updating includes configuration '
                          'with new tasks: {0}'.format(tasks))
        if not os.path.isfile(self.includes_path):
            raise errors.DaemonNotConfiguredError(self.name)
        with open(self.includes_path) as include_file:
            includes = include_file.read()
        if includes:
            # append to current includes
            new_includes = '{0},{1}'.format(includes, tasks)
        else:
            # current includes is empty
            new_includes = tasks

        if os.path.exists(self.includes_path):
            os.remove(self.includes_path)

        with open(self.includes_path, 'w') as f:
            f.write(new_includes)

    def stop_command(self):
        return stop_command(self)

    def start_command(self):
        return start_command(self)

    def _create_includes(self):

        dirname = os.path.dirname(self.includes_path)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        open(self.includes_path, 'w').close()

        # register plugins
        for plugin in self.plugins:
            self.register(plugin)

        # add built-in operations
        self.update_includes(
            ','.join(operations.CLOUDIFY_AGENT_BUILT_IN_TASK_MODULES))

    def _create_script(self):
        rendered = utils.render_template_to_file(
            template_path='pm/initd/initd.template',
            daemon_name=self.name,
            config_path=self.config_path
        )
        self.runner.run('sudo cp {0} {1}'.format(rendered, self.script_path))
        self.runner.run('sudo rm {0}'.format(rendered))
        self.runner.run('sudo chmod +x {0}'.format(self.script_path))

    def _create_config(self):
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
            storage_dir=utils.get_storage_directory()
        )

        self.runner.run('sudo cp {0} {1}'.format(rendered, self.config_path))
        self.runner.run('sudo rm {0}'.format(rendered))

    def _create_start_on_boot_entry(self):

        def _handle_debian():
            self.runner.run('sudo update-rc.d {0} defaults'.format(self.name))

        def _handle_rpm():
            self.runner.run('sudo /sbin/chkconfig --add {0}'.format(self.name))
            self.runner.run('sudo /sbin/chkconfig {0} on'.format(self.name))

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


def start_command(daemon):
    return 'sudo service {0} start'.format(daemon.name)


def stop_command(daemon):
    return 'sudo service {0} stop'.format(daemon.name)
