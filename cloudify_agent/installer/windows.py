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

import shutil
import urllib
import tempfile
from setuptools import archive_util

from cloudify.utils import LocalCommandRunner

from cloudify_agent.installer.runners.winrm_runner import WinRMRunner
from cloudify_agent.installer import AgentInstaller
from cloudify_agent.api import utils


class RemoteWindowsAgentInstaller(AgentInstaller):

    def __init__(self, cloudify_agent, logger=None):
        super(RemoteWindowsAgentInstaller, self).__init__(
            cloudify_agent, logger)
        self.cfy_agent_path = '{0}\\Scripts\\cfy-agent'.format(
            self.cloudify_agent['envdir'])
        self.runner = WinRMRunner(
            host=cloudify_agent['ip'],
            user=cloudify_agent['user'],
            password=cloudify_agent['password'],
            port=cloudify_agent.get('port'),
            protocol=cloudify_agent.get('protocol'),
            uri=cloudify_agent.get('user'),
            logger=self.logger)

    @property
    def downloader(self):
        return self.runner.download

    @property
    def extractor(self):
        return self.runner.unzip

    def _run_agent_command(self, command, execution_env=None):

        if execution_env is None:
            execution_env = {}

        response = self.runner.run(
            command='{0} {1}'.format(self.cfy_agent_path, command),
            execution_env=execution_env)
        if response.output:
            for line in response.output.splitlines():
                self.logger.info(line)
        return response

    def _run_daemon_command(self, command,
                            execution_env=None):

        return self._run_agent_command(
            command='daemons {0} --name={1}'
            .format(command, self.cloudify_agent['name']),
            execution_env=execution_env)

    def create_agent(self):
        if 'source_url' in self.cloudify_agent:
            self._from_source()
        else:
            self._from_package()
        self._run_daemon_command(
            'create {0}'.format(self._create_process_management_options()),
            execution_env=self._create_agent_env())

    def configure_agent(self):
        self._run_daemon_command('configure')

    def start_agent(self):
        self._run_daemon_command('start')

    def stop_agent(self):
        self._run_daemon_command('stop')

    def delete_agent(self):
        self._run_daemon_command('delete')
        self.runner.delete(self.cloudify_agent['agent_dir'],
                           ignore_missing=True)

    def restart_agent(self):
        self._run_daemon_command('restart')

    def create_custom_env_file_on_target(self, environment):
        env_file = utils.env_to_file(env_variables=environment)
        if env_file:
            return self.runner.put_file(src=env_file)
        else:
            return None

    def close(self):
        pass

    def _from_source(self):

        get_pip_url = 'https://bootstrap.pypa.io/get-pip.py'

        requirements = self.cloudify_agent.get('requirements')
        source_url = self.cloudify_agent['source_url']

        get_pip = self.downloader(get_pip_url)

        self.logger.info('Installing pip...')
        self.runner.run('python {0}'.format(get_pip))
        self.logger.info('Installing virtualenv...')
        self.runner.run('pip install virtualenv')

        self.logger.info('Creating virtualenv at {0}'.format(
            self.cloudify_agent['envdir']))
        self.runner.run('virtualenv {0}'.format(
            self.cloudify_agent['envdir']))

        pip_path = '{0}\\Scripts\\pip'.format(self.cloudify_agent['envdir'])

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
        package_path = self.downloader(
            url=self.cloudify_agent['package_url'])
        self.logger.info('Untaring Agent package...')
        self.extractor(archive=package_path,
                       destination=self.cloudify_agent['agent_dir'])
        configure = '--relocated-env'
        if self.cloudify_agent['disable_requiretty']:
            configure = '{0} --disable-requiretty'.format(configure)
        self._run_agent_command('configure {0}'.format(configure))


class LocalWindowsAgentInstaller(RemoteWindowsAgentInstaller):

    def __init__(self, cloudify_agent, logger=None):
        super(RemoteWindowsAgentInstaller, self).__init__(cloudify_agent,
                                                          logger)
        self.cfy_agent_path = '{0}\\Scripts\\cfy-agent'.format(
            cloudify_agent['envdir'])
        self.runner = LocalCommandRunner(logger=logger)

    def create_custom_env_file_on_target(self, environment):
        return utils.env_to_file(env_variables=environment, posix=False)

    def close_installer(self):
        pass

    @property
    def downloader(self):

        def _download(url, output_path=None):
            if output_path is None:
                output_path = tempfile.mkstemp()[1]
            urllib.urlretrieve(url, output_path)
            return output_path

        return _download

    @property
    def extractor(self):

        def _unzip(archive, destination=None):

            if destination is None:
                destination = tempfile.mkdtemp()
            archive_util.unpack_zipfile(archive, destination)
            return destination

        return _unzip

    def delete_agent(self):
        self._run_daemon_command('delete')
        shutil.rmtree(self.cloudify_agent['agent_dir'])
