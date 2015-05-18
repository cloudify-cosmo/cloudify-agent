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

import os
import urllib
import tempfile

from cloudify.utils import LocalCommandRunner

from cloudify_agent.installer import AgentInstaller
from cloudify_agent.api import utils


class RemoteLinuxAgentInstaller(AgentInstaller):

    def __init__(self, cloudify_agent, logger=None):
        super(RemoteLinuxAgentInstaller, self).__init__(
            cloudify_agent, logger)
        self.cfy_agent_path = '{0}/bin/python {0}/bin/cfy-agent'.format(
            cloudify_agent['envdir'])

        # importing fabric stuff is a bit expensive and kind of shaky
        # because the import may fail on windows boxes that don't the pywin32
        # extensions installed. so lets import only when we really have to.

        from cloudify_agent.installer.runners.fabric_runner \
            import FabricRunner
        self.runner = FabricRunner(
            logger=self.logger,
            host=cloudify_agent['ip'],
            user=cloudify_agent['user'],
            port=cloudify_agent.get('port'),
            key=cloudify_agent.get('key'),
            password=cloudify_agent.get('password'),
            fabric_env=cloudify_agent.get('fabric_env'))

    @property
    def download(self):
        return self.runner.download

    @property
    def untar(self):
        return self.runner.untar

    def _run_agent_command(self, command, execution_env=None, sudo=True):

        if execution_env is None:
            execution_env = {}

        full_command = '{0} {1}'.format(self.cfy_agent_path, command)
        if sudo:
            full_command = 'sudo {0}'.format(full_command)

        return self.runner.run(
            command=full_command,
            execution_env=execution_env)

    def _run_daemon_command(self, command,
                            execution_env=None,
                            sudo=True):

        full_command = 'daemons {0} --name={1}'.format(
            command, self.cloudify_agent['name'])

        return self._run_agent_command(command=full_command,
                                       execution_env=execution_env,
                                       sudo=sudo)

    def create_custom_env_file_on_target(self, environment):
        env_file = utils.env_to_file(env_variables=environment)
        return self.runner.put_file(src=env_file)

    def create(self):
        if 'source_url' in self.cloudify_agent:
            self._from_source()
        else:
            self._from_package()
        self._run_daemon_command(
            'create {0}'.format(self._create_process_management_options()),
            execution_env=self._create_agent_env(), sudo=False)

    def configure(self):
        self._run_daemon_command('configure')

    def start(self):
        self._run_daemon_command('start')

    def stop(self):
        self._run_daemon_command('stop')

    def delete(self):
        self._run_daemon_command('delete')
        self.runner.run('rm -rf {0}'.format(self.cloudify_agent['agent_dir']))

    def restart(self):
        self._run_daemon_command('restart')

    def close_installer(self):
        self.runner.close()

    def _from_source(self):

        get_pip_url = 'https://bootstrap.pypa.io/get-pip.py'

        requirements = self.cloudify_agent.get('requirements')
        source_url = self.cloudify_agent['source_url']

        get_pip = self.download(get_pip_url)

        self.logger.info('Installing pip...')
        self.runner.run('sudo python {0}'.format(get_pip))
        self.logger.info('Installing virtualenv...')
        self.runner.run('sudo pip install virtualenv')

        self.logger.info('Creating virtualenv at {0}'.format(
            self.cloudify_agent['envdir']))
        self.runner.run('virtualenv {0}'.format(self.cloudify_agent[
            'envdir']))

        pip_path = '{0}/bin/pip'.format(self.cloudify_agent['envdir'])

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

        package_path = self.download(
            url=self.cloudify_agent['package_url'])
        self.logger.info('Untaring Agent package...')
        self.untar(archive=package_path,
                   destination=self.cloudify_agent['agent_dir'])
        configure = '--relocated-env'
        if self.cloudify_agent['disable_requiretty']:
            configure = '{0} --disable-requiretty'.format(configure)
        self._run_agent_command('configure {0}'.format(configure))


class LocalLinuxAgentInstaller(RemoteLinuxAgentInstaller):

    def __init__(self, cloudify_agent, logger=None):
        super(RemoteLinuxAgentInstaller, self).__init__(cloudify_agent, logger)
        self.cfy_agent_path = '{0}/bin/python {0}/bin/cfy-agent'.format(
            cloudify_agent['envdir'])
        self.runner = LocalCommandRunner(logger=logger)

    def create_custom_env_file_on_target(self, environment):
        return utils.env_to_file(env_variables=environment)

    def close_installer(self):
        pass

    @property
    def download(self):

        def _download(url, output_path=None):
            if output_path is None:
                output_path = tempfile.mkstemp()[1]
            urllib.urlretrieve(url, output_path)
            self.logger.info('Downloaded {0} to {1}'.format(url, output_path))
            return output_path

        return _download

    @property
    def untar(self):

        def _untar(archive, destination, strip=1):
            if not os.path.exists(destination):
                os.makedirs(destination)
            self.runner.run('tar xzvf {0} --strip={1} -C {2}'
                            .format(archive, strip, destination))
        return _untar
