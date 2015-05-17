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
from functools import wraps

from cloudify import ctx
from cloudify.state import current_ctx

from cloudify_agent.installer.config import configuration
from cloudify_agent.installer.runners.local_runner import LocalRunner


def init_agent_installer(func):

    @wraps(func)
    def wrapper(*args, **kwargs):

        cloudify_agent = kwargs.get('cloudify_agent', {})

        # set connection details
        configuration.prepare_connection(cloudify_agent)

        # now we can create the runner and attach it to ctx
        if cloudify_agent['local']:
            runner = LocalRunner(logger=ctx.logger)
        elif cloudify_agent['windows']:

            # import here to avoid importing winrm related stuff when they
            # are not needed
            from cloudify_agent.installer.runners.winrm_runner import \
                WinRMRunner
            runner = WinRMRunner(
                host=cloudify_agent['ip'],
                user=cloudify_agent['user'],
                password=cloudify_agent['password'],
                port=cloudify_agent.get('port'),
                protocol=cloudify_agent.get('protocol'),
                uri=cloudify_agent.get('user'),
                logger=ctx.logger)
        else:
            # import here because simply importing this module on a
            # windows box will fail if the pywin32 extensions are not
            # installed. see http://sourceforge.net/projects/pywin32/
            from cloudify_agent.installer.runners.fabric_runner import \
                FabricRunner
            runner = FabricRunner(
                logger=ctx.logger,
                host=cloudify_agent['ip'],
                user=cloudify_agent['user'],
                port=cloudify_agent.get('port'),
                key=cloudify_agent.get('key'),
                password=cloudify_agent.get('password'),
                fabric_env=cloudify_agent.get('fabric_env'))

        setattr(current_ctx.get_ctx(), 'runner', runner)

        configuration.prepare_agent(cloudify_agent)
        agent_runner = AgentCommandRunner(cloudify_agent)
        setattr(current_ctx.get_ctx(), 'agent', agent_runner)

        kwargs['cloudify_agent'] = cloudify_agent

        try:
            return func(*args, **kwargs)
        finally:
            runner.close()

    return wrapper


class AgentCommandRunner(object):

    """
    class for running cloudify agent commands based on the configuration.
    this class simplifies the agent commands by automatically prefixing the
    correct virtualenv to run commands under.

    """

    def __init__(self, cloudify_agent):
        self._cloudify_agent = cloudify_agent
        self.agent_dir = cloudify_agent['agent_dir']
        bin_path = '{0}/env/bin'.format(self.agent_dir)
        self._prefix = '{0}/python {0}/cfy-agent'.format(bin_path)

    def run(self, command, execution_env=None):
        response = ctx.runner.run(
            '{0} {1}'.format(self._prefix, command),
            execution_env=execution_env)
        if response.output:
            for line in response.output.split(os.linesep):
                ctx.logger.info(line)

    def sudo(self, command):
        response = ctx.runner.sudo(
            '{0} {1}'.format(self._prefix, command))
        if response.output:
            for line in response.output.split(os.linesep):
                ctx.logger.info(line)

    def from_source(self):
        get_pip_url = 'https://bootstrap.pypa.io/get-pip.py'

        requirements = self._cloudify_agent.get('requirements')
        source_url = self._cloudify_agent['source_url']

        get_pip = ctx.runner.download(get_pip_url)

        if self._cloudify_agent['windows']:
            elevated = ctx.runner.run
        else:
            elevated = ctx.runner.sudo

        ctx.logger.info('Installing pip...')
        elevated('python {0}'.format(get_pip))
        ctx.logger.info('Installing virtualenv...')
        elevated('pip install virtualenv')

        env_path = '{0}/env'.format(self._cloudify_agent['agent_dir'])
        ctx.logger.info('Creating virtualenv at {0}'.format(env_path))
        ctx.runner.run('virtualenv {0}'.format(env_path))
        if requirements:
            ctx.logger.info('Installing requirements file: {0}'
                            .format(requirements))
            ctx.runner.run('{0}/bin/pip install -r {1}'
                           .format(env_path, requirements))
        ctx.logger.info('Installing Cloudify Agent from {0}'
                        .format(source_url))
        ctx.runner.run('{0}/bin/pip install {1}'
                       .format(env_path, source_url))

    def from_package(self):
        package_path = ctx.runner.download(
            url=self._cloudify_agent['package_url'])
        ctx.logger.info('Extracting Agent package...')
        ctx.runner.extract(archive=package_path,
                           destination=self._cloudify_agent['agent_dir'])

        ctx.logger.info('Auto-correcting agent virtualenv')
        ctx.agent.run('configure --relocated-env')

    def delete(self):
        ctx.logger.info('Deleting Agent Package')
        ctx.runner.delete(self.agent_dir)
