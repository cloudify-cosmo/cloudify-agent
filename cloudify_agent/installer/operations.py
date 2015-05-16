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

import copy

from cloudify.decorators import operation
from cloudify import ctx

from cloudify_agent.installer import init_agent_installer
from cloudify_agent.installer import utils
from cloudify_agent.shell import env


@operation
@init_agent_installer
def create(cloudify_agent, **_):

    # save runtime properties immediately so that they will be available
    # to other operation even in case the create failed.
    _set_runtime_properties(cloudify_agent)

    def _create_agent_env_path():
        local_env_path = utils.env_to_file(cloudify_agent.get('env', {}))
        return ctx.runner.put_file(local_env_path)

    def _create_execution_env(_agent_env_path):

        return {

            # mandatory values calculated before the agent
            # is actually created
            env.CLOUDIFY_MANAGER_IP: cloudify_agent['manager_ip'],
            env.CLOUDIFY_DAEMON_QUEUE: cloudify_agent['queue'],
            env.CLOUDIFY_DAEMON_NAME: cloudify_agent['name'],

            # these are variables that have default values that will be set
            # by the agent on the remote host if not set here
            env.CLOUDIFY_DAEMON_USER: cloudify_agent.get('user'),
            env.CLOUDIFY_BROKER_IP: cloudify_agent.get('broker_ip'),
            env.CLOUDIFY_BROKER_PORT: cloudify_agent.get('broker_port'),
            env.CLOUDIFY_BROKER_URL: cloudify_agent.get('broker_url'),
            env.CLOUDIFY_DAEMON_GROUP: cloudify_agent.get('group'),
            env.CLOUDIFY_MANAGER_PORT: cloudify_agent.get('manager_port'),
            env.CLOUDIFY_DAEMON_MAX_WORKERS: cloudify_agent.get(
                'max_workers'),
            env.CLOUDIFY_DAEMON_MIN_WORKERS: cloudify_agent.get(
                'min_workers'),
            env.CLOUDIFY_DAEMON_PROCESS_MANAGEMENT:
                cloudify_agent['process_management']['name'],
            env.CLOUDIFY_DAEMON_WORKDIR: cloudify_agent['workdir'],
            env.CLOUDIFY_DAEMON_EXTRA_ENV: _agent_env_path
        }

    agent_env_path = _create_agent_env_path()
    execution_env = _create_execution_env(agent_env_path)
    execution_env = utils.purge_none_values(execution_env)
    execution_env = utils.stringify_values(execution_env)

    ctx.logger.debug('Cloudify Agent will be created using the following '
                     'environment: {0}'.format(execution_env))

    if 'source_url' in cloudify_agent:
        ctx.agent.from_source()
    else:
        ctx.agent.from_package()

    ctx.logger.info('Creating Agent...')
    ctx.agent.run('daemons create', execution_env=execution_env)


@operation
@init_agent_installer
def configure(cloudify_agent, **_):
    ctx.logger.info('Configuring Agent...')
    custom_options = _create_custom_process_management_options(cloudify_agent)
    ctx.agent.run('daemons configure --name={0} {1}'
                  .format(cloudify_agent['name'], custom_options))


@operation
@init_agent_installer
def start(cloudify_agent, **_):
    ctx.logger.info('Starting Agent...')
    ctx.agent.sudo('daemons start --name={0}'.format(cloudify_agent['name']))


@operation
@init_agent_installer
def restart(cloudify_agent, **_):
    ctx.logger.info('Restarting Agent...')
    ctx.agent.sudo('daemons restart --name={0}'.format(cloudify_agent['name']))


@operation
@init_agent_installer
def stop(cloudify_agent, **_):
    ctx.logger.info('Stopping Agent...')
    ctx.agent.sudo('daemons stop --name={0}'.format(cloudify_agent['name']))


@operation
@init_agent_installer
def delete(cloudify_agent, **_):
    ctx.logger.info('Deleting Agent...')
    ctx.agent.run('daemons delete --name={0}'.format(cloudify_agent['name']))

    # now we need to delete the package itself, this cannot be done via
    # the cfy-agent cli because we are actually deleting the cli itself.
    ctx.agent.delete()


def _set_runtime_properties(cloudify_agent):
    ctx.instance.runtime_properties['cloudify_agent'] = cloudify_agent


def _create_custom_process_management_options(cloudify_agent):
    options = []
    process_management = copy.deepcopy(cloudify_agent['process_management'])

    # remove the name key because it is
    # actually passed separately via an
    # environment variable
    process_management.pop('name')
    for key, value in process_management.iteritems():
        options.append('--{0}={1}'.format(key, value))
    return ' '.join(options)
