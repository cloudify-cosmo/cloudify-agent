#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
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

import tempfile
import shutil
import urllib
import os
import copy
from functools import wraps

from cloudify import ctx
from cloudify.state import current_ctx
from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner

from cloudify_agent.installer.config import configuration
from cloudify_agent.api import utils
from cloudify_agent.installer.config.attributes import AGENT_ATTRIBUTES
from cloudify_agent.installer.config.attributes import raise_missing_attribute
from cloudify_agent.shell import env


def init_agent_installer(func):

    # import here to avoid circular dependency
    from cloudify_agent.installer.runners import fabric_runner
    from cloudify_agent.installer.runners import winrm_runner
    from cloudify_agent.installer import linux
    from cloudify_agent.installer import windows

    @wraps(func)
    def wrapper(*args, **kwargs):

        cloudify_agent = kwargs.get('cloudify_agent', {})

        ctx.logger.debug('Processing connection configuration. '
                         '[cloudify_agent={0}] '
                         .format(cloudify_agent))
        # first prepare all connection details
        cloudify_agent = configuration.prepare_connection(cloudify_agent)
        ctx.logger.debug('Processed [cloudify_agent={0}]'
                         .format(cloudify_agent))

        # create the correct runner according to os
        # and local/remote execution. we need this runner now because it
        # will be used to determine the agent basedir in case it wasn't
        # explicitly set
        if cloudify_agent['local']:
            runner = LocalCommandRunner(logger=ctx.logger)
        else:
            if cloudify_agent['windows']:
                runner = winrm_runner.WinRMRunner(
                    host=cloudify_agent['ip'],
                    user=cloudify_agent['user'],
                    password=cloudify_agent['password'],
                    port=cloudify_agent.get('port'),
                    protocol=cloudify_agent.get('protocol'),
                    uri=cloudify_agent.get('user'),
                    logger=ctx.logger)
            else:
                runner = fabric_runner.FabricRunner(
                    logger=ctx.logger,
                    host=cloudify_agent['ip'],
                    user=cloudify_agent['user'],
                    port=cloudify_agent.get('port'),
                    key=cloudify_agent.get('key'),
                    password=cloudify_agent.get('password'),
                    fabric_env=cloudify_agent.get('fabric_env'))

        setattr(current_ctx.get_ctx(), 'runner', runner)

        ctx.logger.debug('Processing agent configuration. '
                         '[cloudify_agent={0}] '
                         .format(cloudify_agent))
        # now we can create all other agent attributes
        cloudify_agent = configuration.prepare_agent(cloudify_agent)
        ctx.logger.debug('Processed [cloudify_agent={0}]'
                         .format(cloudify_agent))

        # now we can validate mandatory attributes
        for attr, value in AGENT_ATTRIBUTES.iteritems():
            mandatory = value.get('mandatory', False)
            if mandatory and attr not in cloudify_agent:
                raise_missing_attribute(attr)

        # create the correct installer according to os
        # and local/remote execution
        if cloudify_agent['local']:
            if os.name == 'nt':
                installer = windows.LocalWindowsAgentInstaller(
                    cloudify_agent, ctx.logger)
            else:
                installer = linux.LocalLinuxAgentInstaller(
                    cloudify_agent, ctx.logger)
        elif cloudify_agent['windows']:
            installer = windows.RemoteWindowsAgentInstaller(
                cloudify_agent, ctx.logger)
        else:
            installer = linux.RemoteLinuxAgentInstaller(
                cloudify_agent, ctx.logger)

        setattr(current_ctx.get_ctx(), 'installer', installer)

        kwargs['cloudify_agent'] = cloudify_agent

        try:
            return func(*args, **kwargs)
        finally:
            # we need to close fabric connection
            if isinstance(installer, linux.RemoteLinuxAgentInstaller):
                installer.runner.close()

    return wrapper


class AgentInstaller(object):

    def __init__(self, cloudify_agent, logger=None):
        self.cloudify_agent = cloudify_agent
        self.logger = logger or setup_logger(self.__class__.__name__)

    def run_agent_command(self, command, execution_env=None):
        if execution_env is None:
            execution_env = {}
        response = self.runner.run(
            command='{0} {1}'.format(self.cfy_agent_path, command),
            execution_env=execution_env)
        if response.output:
            for line in response.output.splitlines():
                self.logger.info(line)
        return response

    def run_daemon_command(self, command,
                           execution_env=None):
        return self.run_agent_command(
            command='daemons {0} --name={1}'
            .format(command, self.cloudify_agent['name']),
            execution_env=execution_env)

    def create_agent(self):
        if 'source_url' in self.cloudify_agent:
            self.logger.info('Creating agent from source')
            self._from_source()
        else:
            self.logger.info('Creating agent from package')
            self._from_package()
        self.run_daemon_command(
            command='create {0}'
            .format(self._create_process_management_options()),
            execution_env=self._create_agent_env())

    def configure_agent(self):
        self.run_daemon_command('configure')

    def start_agent(self):
        self.run_daemon_command('start')

    def stop_agent(self):
        self.run_daemon_command('stop')

    def delete_agent(self):
        self.run_daemon_command('delete')
        self.runner.delete(self.cloudify_agent['agent_dir'])

    def restart_agent(self):
        self.run_daemon_command('restart')

    def _from_source(self):

        requirements = self.cloudify_agent.get('requirements')
        source_url = self.cloudify_agent['source_url']

        self.logger.info('Installing pip...')
        pip_path = self.install_pip()
        self.logger.info('Installing virtualenv...')
        self.install_virtualenv()

        self.logger.info('Creating virtualenv at {0}'.format(
            self.cloudify_agent['envdir']))
        self.runner.run('virtualenv {0}'.format(
            self.cloudify_agent['envdir']))

        if requirements:
            self.logger.info('Installing requirements file: {0}'
                             .format(requirements))
            self.runner.run('{0} install -r {1}'
                            .format(pip_path, requirements))
        self.logger.info('Installing Cloudify Agent from {0}'
                         .format(source_url))
        self.runner.run('{0} install {1}'
                        .format(pip_path, source_url))

    def _from_package(self):

        self.logger.info('Downloading Agent Package from {0}'.format(
            self.cloudify_agent['package_url']
        ))
        package_path = self.download(
            url=self.cloudify_agent['package_url'])
        self.logger.info('Untaring Agent package...')
        self.extract(archive=package_path,
                     destination=self.cloudify_agent['agent_dir'])
        configure = '--relocated-env'
        if self.cloudify_agent.get('disable_requiretty') is True:
            configure = '{0} --disable-requiretty'.format(configure)
        self.run_agent_command('configure {0}'.format(configure))

    def download(self, url):
        raise NotImplementedError('Must be implemented by sub-class')

    def extract(self, archive, destination):
        raise NotImplementedError('Must be implemented by sub-class')

    def install_pip(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def install_virtualenv(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def create_custom_env_file_on_target(self, environment):
        raise NotImplementedError('Must be implemented by sub-class')

    @property
    def runner(self):
        raise NotImplementedError('Must be implemented by sub-class')

    @property
    def cfy_agent_path(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def _create_agent_env(self):

        execution_env = {

            # mandatory values calculated before the agent
            # is actually created
            env.CLOUDIFY_MANAGER_IP: self.cloudify_agent['manager_ip'],
            env.CLOUDIFY_DAEMON_QUEUE: self.cloudify_agent['queue'],
            env.CLOUDIFY_DAEMON_NAME: self.cloudify_agent['name'],

            # these are variables that have default values that will be set
            # by the agent on the remote host if not set here
            env.CLOUDIFY_DAEMON_USER: self.cloudify_agent.get('user'),
            env.CLOUDIFY_BROKER_IP: self.cloudify_agent.get('broker_ip'),
            env.CLOUDIFY_BROKER_PORT: self.cloudify_agent.get('broker_port'),
            env.CLOUDIFY_BROKER_URL: self.cloudify_agent.get('broker_url'),
            env.CLOUDIFY_MANAGER_PORT: self.cloudify_agent.get('manager_port'),
            env.CLOUDIFY_DAEMON_MAX_WORKERS: self.cloudify_agent.get(
                'max_workers'),
            env.CLOUDIFY_DAEMON_MIN_WORKERS: self.cloudify_agent.get(
                'min_workers'),
            env.CLOUDIFY_DAEMON_PROCESS_MANAGEMENT:
                self.cloudify_agent['process_management']['name'],
            env.CLOUDIFY_DAEMON_WORKDIR: self.cloudify_agent['workdir'],
            env.CLOUDIFY_DAEMON_EXTRA_ENV:
                self.create_custom_env_file_on_target(
                    self.cloudify_agent.get('env', {}))
        }

        execution_env = utils.purge_none_values(execution_env)
        execution_env = utils.stringify_values(execution_env)

        ctx.logger.debug('Cloudify Agent will be created using the following '
                         'environment: {0}'.format(execution_env))

        return execution_env

    def _create_process_management_options(self):
        options = []
        process_management = copy.deepcopy(self.cloudify_agent[
            'process_management'])

        # remove the name key because it is
        # actually passed separately via an
        # environment variable
        process_management.pop('name')
        for key, value in process_management.iteritems():
            options.append('--{0}={1}'.format(key, value))
        return ' '.join(options)


class WindowsInstallerMixin(AgentInstaller):

    @property
    def cfy_agent_path(self):
        return '{0}\\Scripts\\cfy-agent'.format(
            self.cloudify_agent['envdir'])

    def install_pip(self):
        get_pip_url = 'https://bootstrap.pypa.io/get-pip.py'
        get_pip = self.download(get_pip_url)
        self.runner.run('python {0}'.format(get_pip))
        return '{0}\\Scripts\\pip'.format(self.cloudify_agent['envdir'])

    def install_virtualenv(self):
        self.runner.run('pip install virtualenv')


class LinuxInstallerMixin(AgentInstaller):

    @property
    def cfy_agent_path(self):
        return '{0}/bin/python {0}/bin/cfy-agent'.format(
            self.cloudify_agent['envdir'])

    def install_pip(self):
        get_pip_url = 'https://bootstrap.pypa.io/get-pip.py'
        get_pip = self.download(get_pip_url)
        self.runner.run('sudo python {0}'.format(get_pip))
        return '{0}/bin/pip'.format(self.cloudify_agent['envdir'])

    def install_virtualenv(self):
        self.runner.run('sudo pip install virtualenv')


class LocalInstallerMixin(AgentInstaller):

    @property
    def runner(self):
        return LocalCommandRunner(logger=self.logger)

    def download(self, url):
        output_path = tempfile.mkstemp()[1]
        urllib.urlretrieve(url, output_path)
        return output_path

    def delete_agent(self):
        self.run_daemon_command('delete')
        shutil.rmtree(self.cloudify_agent['agent_dir'])

    def create_custom_env_file_on_target(self, environment):
        posix = not self.cloudify_agent['windows']
        self.logger.debug('Creating a environment file from {0}'
                          .format(environment))
        return utils.env_to_file(env_variables=environment, posix=posix)


class RemoteInstallerMixin(AgentInstaller):

    def create_custom_env_file_on_target(self, environment):
        posix = not self.cloudify_agent['windows']
        env_file = utils.env_to_file(env_variables=environment, posix=posix)
        if env_file:
            return self.runner.put_file(src=env_file)
        else:
            return None

    def download(self, url):
        return self.runner.download(url)
