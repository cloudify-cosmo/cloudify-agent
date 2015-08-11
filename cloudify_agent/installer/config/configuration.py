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

import getpass
import os
import platform

from cloudify import ctx
from cloudify import context
from cloudify.utils import get_manager_ip
from cloudify.utils import get_manager_file_server_url

from cloudify_agent.api import utils
from cloudify_agent.installer.config.decorators import group
from cloudify_agent.installer.config.attributes import raise_missing_attribute
from cloudify_agent.installer.config.attributes import raise_missing_attributes


def prepare_connection(cloudify_agent):
    connection_attributes(cloudify_agent)


def prepare_agent(cloudify_agent, runner):
    cfy_agent_attributes(cloudify_agent)
    installation_attributes(cloudify_agent, runner)


@group('connection')
def connection_attributes(cloudify_agent):

    if 'local' not in cloudify_agent:
        cloudify_agent['local'] = ctx.type == context.DEPLOYMENT

    if cloudify_agent['local']:

        # if installing an agent locally, we auto-detect which
        # os the agent is dedicated for
        cloudify_agent['windows'] = os.name == 'nt'

        # if installing locally, we install the agent with the same user the
        # current agent is running under. we don't care about any other
        # connection details
        if 'user' not in cloudify_agent:
            cloudify_agent['user'] = getpass.getuser()
    else:

        if 'windows' not in cloudify_agent:

            if ctx.plugin == 'windows_agent_installer':
                # 3.2 Compute node, installing windows
                cloudify_agent['windows'] = True
            if ctx.plugin == 'agent_installer':
                # 3.2 Compute node, installing linux
                cloudify_agent['windows'] = False
            if ctx.plugin == 'agent':
                # 3.3 Compute node, determine by new property 'os'
                cloudify_agent['windows'] = ctx.node.properties[
                    'os_family'].lower() == 'windows'

        if 'ip' not in cloudify_agent:

            # support 'ip' attribute as direct node property or runtime
            # property (as opposed to nested inside the cloudify_agent dict)
            ip = ctx.instance.runtime_properties.get('ip')
            if not ip:
                ip = ctx.node.properties.get('ip')
            if not ip:
                raise_missing_attribute('ip')
            cloudify_agent['ip'] = ip

        if 'password' not in cloudify_agent:

            # support password as direct node property or runtime
            # property (as opposed to nested inside the cloudify_agent dict)
            password = ctx.instance.runtime_properties.get('password')
            if not password:
                password = ctx.node.properties.get('password')
            if not password and cloudify_agent['windows']:
                # a remote windows installation requires a
                # password to connect to the machine
                raise_missing_attribute('password')
            cloudify_agent['password'] = password

        # a remote installation requires the username
        # that the agent will run under.
        if 'user' not in cloudify_agent:
            raise_missing_attribute('user')

        # a remote installation requires the ip to connect to.
        if 'ip' not in cloudify_agent:
            raise_missing_attribute('ip')

        # a remote linux installation requires either a password or a key file
        # in order to connect to the remote machine.
        if not cloudify_agent['windows'] and 'password' not in \
                cloudify_agent and 'key' not in cloudify_agent:
            raise_missing_attributes('key', 'password')


@group('cfy-agent')
def cfy_agent_attributes(cloudify_agent):

    if 'process_management' not in cloudify_agent:

        # user did not specify process management configuration, choose the
        # default one according to os type.
        if cloudify_agent['windows']:
            cloudify_agent['process_management'] = {
                'name': 'nssm'
            }
        else:
            cloudify_agent['process_management'] = {
                'name': 'init.d'
            }

    if 'name' not in cloudify_agent:
        if cloudify_agent['local']:
            workflows_worker = cloudify_agent.get('workflows_worker', False)
            suffix = '_workflows' if workflows_worker else ''
            name = '{0}{1}'.format(ctx.deployment.id, suffix)
        else:
            name = ctx.instance.id
        cloudify_agent['name'] = name

    if 'queue' not in cloudify_agent:

        # by default, the queue of the agent is the same as the name
        cloudify_agent['queue'] = cloudify_agent['name']

    if 'manager_ip' not in cloudify_agent:

        # by default, the manager ip will be set by an environment variable
        cloudify_agent['manager_ip'] = get_manager_ip()


@group('installation')
def installation_attributes(cloudify_agent, runner):

    if 'source_url' not in cloudify_agent:

        if 'package_url' not in cloudify_agent:

            if cloudify_agent['windows']:

                # no distribution difference in windows installation
                cloudify_agent['package_url'] = '{0}/packages/agents' \
                                                '/cloudify-windows-agent.exe'\
                    .format(get_manager_file_server_url())
            else:
                # build one from distro and distro_codename
                if cloudify_agent['local']:
                    cloudify_agent['distro'] = platform.dist()[0].lower()
                else:
                    dist = runner.machine_distribution()
                    cloudify_agent['distro'] = dist[0].lower()

                # distro was not specified, try to auto-detect
                if cloudify_agent['local']:
                    cloudify_agent['distro_codename'] = platform.dist()[
                        2].lower()
                else:
                    dist = runner.machine_distribution()
                    cloudify_agent['distro_codename'] = dist[2].lower()

                cloudify_agent['package_url'] = '{0}/packages/agents' \
                                                '/{1}-{2}-agent.tar.gz' \
                    .format(get_manager_file_server_url(),
                            cloudify_agent['distro'],
                            cloudify_agent['distro_codename'])

    if 'basedir' not in cloudify_agent:
        if cloudify_agent['local']:
            basedir = utils.get_home_dir(cloudify_agent['user'])
        else:
            if cloudify_agent['windows']:

                # can't seem to figure out how to get the home_dir remotely
                # on windows. same was as fabric wont work because the
                # 'pwd' module does not exists in a windows python
                # installation.
                # TODO - maybe use some environment variables heuristics?
                basedir = 'C:\\Users\\{0}'.format(cloudify_agent['user'])
            else:
                basedir = runner.home_dir(cloudify_agent['user'])
        cloudify_agent['basedir'] = basedir

    if 'agent_dir' not in cloudify_agent:
        name = cloudify_agent['name']
        basedir = cloudify_agent['basedir']
        if cloudify_agent['windows']:
            agent_dir = '{0}\\{1}'.format(basedir, name)
        else:
            agent_dir = os.path.join(basedir, name)
        cloudify_agent['agent_dir'] = agent_dir

    if 'workdir' not in cloudify_agent:
        agent_dir = cloudify_agent['agent_dir']
        if cloudify_agent['windows']:
            workdir = '{0}\\{1}'.format(agent_dir, 'work')
        else:
            workdir = os.path.join(agent_dir, 'work')
        cloudify_agent['workdir'] = workdir

    if 'envdir' not in cloudify_agent:
        agent_dir = cloudify_agent['agent_dir']
        if cloudify_agent['windows']:
            envdir = '{0}\\{1}'.format(agent_dir, 'env')
        else:
            envdir = os.path.join(agent_dir, 'env')
        cloudify_agent['envdir'] = envdir
