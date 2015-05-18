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
import copy
from functools import wraps

from cloudify import ctx
from cloudify.state import current_ctx
from cloudify.utils import setup_logger

from cloudify_agent.installer.config import configuration
from cloudify_agent.shell import env
from cloudify_agent.installer import utils


def init_agent_installer(func):

    # import here to avoid circular dependency
    from cloudify_agent.installer import linux
    from cloudify_agent.installer import windows

    @wraps(func)
    def wrapper(*args, **kwargs):

        cloudify_agent = kwargs.get('cloudify_agent', {})

        # set connection details
        configuration.prepare_connection(cloudify_agent)
        configuration.prepare_agent(cloudify_agent)

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
            installer.close_installer()

    return wrapper


class AgentInstaller(object):

    def __init__(self, cloudify_agent, logger=None):
        self.cloudify_agent = cloudify_agent
        self.logger = logger or setup_logger(self.__class__.__name__)

    def create(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def configure(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def start(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def stop(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def delete(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def restart(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def create_custom_env_file_on_target(self, environment):
        raise NotImplementedError('Must be implemented by sub-class')

    def close(self):
        raise NotImplementedError('Must be implemented by sub-class')

    @property
    def downloader(self):
        raise NotImplementedError('Must be implemented by sub-class')

    @property
    def extractor(self):
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
            env.CLOUDIFY_DAEMON_GROUP: self.cloudify_agent.get('group'),
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
                    self.cloudify_agent['env'])
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
