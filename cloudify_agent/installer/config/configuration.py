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

import copy
import getpass
import os
import platform

from cloudify import ctx
from cloudify import context
from cloudify import utils

from cloudify_agent.installer.config.decorators import group
from cloudify_agent.installer.config.attributes import raise_missing_attribute


class fixed_dict(dict):

    def __setitem__(self, key, value):
        if key in self.keys():
            return
        super(fixed_dict, self).__setitem__(key, value)


def prepare_connection(cloudify_agent):

    fixed_cloudify_agent = fixed_dict(**copy.deepcopy(cloudify_agent))

    ctx.logger.debug('Preparing cloudify_agent connection attributes')
    connection_attributes(fixed_cloudify_agent)

    return copy.deepcopy(fixed_cloudify_agent)


def prepare_agent(cloudify_agent):

    fixed_cloudify_agent = fixed_dict(**copy.deepcopy(cloudify_agent))

    ctx.logger.debug('Preparing cloudify_agent cfy_agent attributes')
    cfy_agent_attributes(fixed_cloudify_agent)
    ctx.logger.debug('Preparing cloudify_agent installation attributes')
    installation_attributes(fixed_cloudify_agent)

    return copy.deepcopy(fixed_cloudify_agent)


@group('cfy-agent')
def cfy_agent_attributes(cloudify_agent):

    if cloudify_agent['windows']:
        cloudify_agent['process_management'] = {'name': 'nssm'}
    else:
        cloudify_agent['process_management'] = {'name': 'init.d'}

    if ctx.type == context.DEPLOYMENT:
        workflows_worker = cloudify_agent.get('workflows_worker', False)
        suffix = '_workflows' if workflows_worker else ''
        queue = '{0}{1}'.format(ctx.deployment.id, suffix)
    else:
        queue = ctx.instance.id
    cloudify_agent['queue'] = queue

    cloudify_agent['name'] = cloudify_agent['queue']

    if 'manager_ip' not in cloudify_agent:

        # double check here because get_manager_ip function will
        # fail we the env variable is not set, but this is ok since
        # the manager_ip might have been explicitly set.
        cloudify_agent['manager_ip'] = utils.get_manager_ip()


@group('connection')
def connection_attributes(cloudify_agent):

    cloudify_agent['local'] = ctx.type == context.DEPLOYMENT

    if cloudify_agent['local']:

        # auto-detect os if running locally
        cloudify_agent['windows'] = os.name == 'nt'

        # we are installing an agent locally, all we need is the username
        if 'user' not in cloudify_agent:

            # default user will be the currently logged user
            cloudify_agent['user'] = getpass.getuser()
    else:
        cloudify_agent['windows'] = False
        # support 'ip' attribute as direct node property or runtime
        # property (as opposed to nested inside the cloudify_agent dict)
        ip = ctx.instance.runtime_properties.get('ip')
        if not ip:
            ip = ctx.node.properties.get('ip')
        if not ip:
            raise_missing_attribute('ip')
        cloudify_agent['ip'] = ip
        if cloudify_agent['windows'] and 'password' not in cloudify_agent:
            raise_missing_attribute('password')


@group('installation')
def installation_attributes(cloudify_agent):

    if 'source_url' not in cloudify_agent:

        # user did not specify package_url, automatically build one from
        # distro and distro_codename
        if cloudify_agent['local']:
            cloudify_agent['distro'] = platform.dist()[0].lower()
        else:
            dist = ctx.runner.machine_distribution()
            cloudify_agent['distro'] = dist[0].lower()

        # distro was not specified, try to auto-detect
        if cloudify_agent['local']:
            cloudify_agent['distro_codename'] = platform.dist()[2].lower()
        else:
            dist = ctx.runner.machine_distribution()
            cloudify_agent['distro_codename'] = dist[2].lower()

        if 'package_url' not in cloudify_agent:
            cloudify_agent['package_url'] = '{0}/packages/agents' \
                                            '/{1}-{2}-agent.tar.gz' \
                .format(utils.get_manager_file_server_url(),
                        cloudify_agent['distro'],
                        cloudify_agent['distro_codename'])

    if cloudify_agent['local']:
        basedir = utils.get_home_dir(cloudify_agent['user'])
    else:
        basedir = ctx.runner.home_dir(cloudify_agent['user'])
    cloudify_agent['basedir'] = basedir

    name = cloudify_agent['name']
    basedir = cloudify_agent['basedir']
    if cloudify_agent['windows']:
        agent_dir = '{0}\\{1}'.format(basedir, name)
    else:
        agent_dir = os.path.join(basedir, name)
    cloudify_agent['agent_dir'] = agent_dir

    agent_dir = cloudify_agent['agent_dir']
    if cloudify_agent['windows']:
        workdir = '{0}\\{1}'.format(agent_dir, 'work')
    else:
        workdir = os.path.join(agent_dir, 'work')
    cloudify_agent['workdir'] = workdir

    agent_dir = cloudify_agent['agent_dir']
    if cloudify_agent['windows']:
        envdir = '{0}\\{1}'.format(agent_dir, 'env')
    else:
        envdir = os.path.join(agent_dir, 'env')
    cloudify_agent['envdir'] = envdir
