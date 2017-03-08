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
from cloudify import constants

from cloudify import utils as cloudify_utils
from cloudify_agent.api import utils as agent_utils
from cloudify_agent.installer import exceptions
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
        cloudify_agent['user'] = getpass.getuser()

        if 'remote_execution' not in cloudify_agent:
            cloudify_agent['remote_execution'] = True
    else:
        if 'remote_execution' not in cloudify_agent:
            install_method = cloudify_utils.internal.get_install_method(
                ctx.node.properties)
            if install_method not in constants.AGENT_INSTALL_METHODS:
                raise exceptions.AgentInstallerConfigurationError(
                    'agent_config.install_method must be one of {0}'
                    ' but found: {1}'.format(constants.AGENT_INSTALL_METHODS,
                                             install_method))
            remote_execution = (install_method ==
                                constants.AGENT_INSTALL_METHOD_REMOTE)
            cloudify_agent.update({
                'remote_execution': remote_execution,
                'install_method': install_method
            })

        if 'windows' not in cloudify_agent:
            if ctx.plugin == 'windows_agent_installer':
                # 3.2 Compute node, installing windows
                cloudify_agent['windows'] = True
            elif ctx.plugin == 'agent_installer':
                # 3.2 Compute node, installing linux
                cloudify_agent['windows'] = False
            else:
                # 3.3 Compute node, determine by new property 'os_family'
                cloudify_agent['windows'] = ctx.node.properties[
                    'os_family'].lower() == 'windows'

        # support 'ip' attribute as direct node property or runtime
        # property (as opposed to nested inside the cloudify_agent dict)
        ip = ctx.instance.runtime_properties.get('ip')
        if not ip:
            ip = ctx.node.properties.get('ip')
        if not ip:
            ip = cloudify_agent.get('ip')
        if not ip and cloudify_agent['remote_execution']:
            # a remote installation requires the ip to connect to.
            raise_missing_attribute('ip')
        if ip:
            cloudify_agent['ip'] = ip

        # support password as direct node property or runtime
        # property (as opposed to nested inside the cloudify_agent dict)
        password = ctx.instance.runtime_properties.get('password')
        if not password:
            password = ctx.node.properties.get('password')
        if not password:
            password = cloudify_agent.get('password')
        if not password and cloudify_agent['windows'] \
                and cloudify_agent['remote_execution']:
            # a remote windows installation requires a
            # password to connect to the machine
            raise_missing_attribute('password')
        if password:
            cloudify_agent['password'] = password

        # a remote installation requires the username
        # that the agent will run under.
        if not cloudify_agent.get('user'):
            raise_missing_attribute('user')

        # a remote linux installation requires either a password or a key file
        # in order to connect to the remote machine.
        if not cloudify_agent['windows'] and \
                not cloudify_agent.get('password') and \
                not cloudify_agent.get('key') and \
                cloudify_agent['remote_execution']:
            raise_missing_attributes('key', 'password')


@group('cfy-agent')
def cfy_agent_attributes(cloudify_agent):
    _cfy_agent_attributes_no_defaults(cloudify_agent)


def _cfy_agent_attributes_no_defaults(cloudify_agent):
    if not cloudify_agent.get('process_management'):
        cloudify_agent['process_management'] = {}

    if not cloudify_agent['process_management'].get('name'):
        # user did not specify process management configuration, choose the
        # default one according to os type.
        if cloudify_agent['windows']:
            name = 'nssm'
        else:
            name = 'init.d'
        cloudify_agent['process_management']['name'] = name

    if not cloudify_agent.get('name'):
        if cloudify_agent['local']:
            workflows_worker = cloudify_agent.get('workflows_worker', False)
            suffix = '_workflows' if workflows_worker else ''
            name = '{0}{1}'.format(ctx.deployment.id, suffix)
        else:
            name = ctx.instance.id
        cloudify_agent['name'] = name

    service_name = cloudify_agent.get('service_name')
    if service_name:
        # service_name takes precedence over name (which is deprecated)
        cloudify_agent['name'] = service_name

    if not cloudify_agent.get('queue'):
        # by default, queue of the agent is the same as the name
        cloudify_agent['queue'] = cloudify_agent['name']

    if not cloudify_agent.get('rest_host'):
        cloudify_agent['rest_host'] = \
            cloudify_utils.get_manager_rest_service_host()

    if not cloudify_agent.get('rest_port'):
        cloudify_agent['rest_port'] = \
            cloudify_utils.get_manager_rest_service_port()

    if not cloudify_agent.get('rest_token'):
        cloudify_agent['rest_token'] = \
            cloudify_utils.get_rest_token()

    if not cloudify_agent.get('rest_tenant'):
        cloudify_agent['rest_tenant'] = \
            cloudify_utils.get_tenant_name()

    if not cloudify_agent.get('bypass_maintenance'):
        cloudify_agent['bypass_maintenance_mode'] = \
            cloudify_utils.get_is_bypass_maintenance()


def directory_attributes(cloudify_agent):
    if not cloudify_agent.get('agent_dir'):
        name = cloudify_agent['name']
        basedir = cloudify_agent['basedir']
        if cloudify_agent['windows']:
            agent_dir = '{0}\\{1}'.format(basedir, name)
        else:
            agent_dir = os.path.join(basedir, name)
        cloudify_agent['agent_dir'] = agent_dir

    if not cloudify_agent.get('workdir'):
        agent_dir = cloudify_agent['agent_dir']
        if cloudify_agent['windows']:
            workdir = '{0}\\{1}'.format(agent_dir, 'work')
        else:
            workdir = os.path.join(agent_dir, 'work')
        cloudify_agent['workdir'] = workdir

    if not cloudify_agent.get('envdir'):
        agent_dir = cloudify_agent['agent_dir']
        if cloudify_agent['windows']:
            envdir = '{0}\\{1}'.format(agent_dir, 'env')
        else:
            envdir = os.path.join(agent_dir, 'env')
        cloudify_agent['envdir'] = envdir

    if not cloudify_agent.get('broker_ssl_cert_path'):
        cloudify_agent['broker_ssl_cert_path'] = \
            cloudify_utils.get_broker_ssl_cert_path()


@group('installation')
def _add_installation_defaults(cloudify_agent):
    pass


@group('cfy-agent')
def _add_cfy_agent_defaults(cloudify_agent):
    pass


def reinstallation_attributes(cloudify_agent):
    _cfy_agent_attributes_no_defaults(cloudify_agent)
    _add_cfy_agent_defaults(cloudify_agent)
    if cloudify_agent.get('basedir'):
        directory_attributes(cloudify_agent)
    _add_installation_defaults(cloudify_agent)


@group('installation')
def installation_attributes(cloudify_agent, runner):

    if (not cloudify_agent.get('source_url') and
            not cloudify_agent.get('package_url')):

        if cloudify_agent['windows']:

            # no distribution difference in windows installation
            cloudify_agent['package_url'] = '{0}/packages/agents' \
                                            '/cloudify-windows-agent.exe'\
                .format(cloudify_utils.get_manager_file_server_url())
        else:
            if not cloudify_agent.get('distro'):
                if cloudify_agent['local']:
                    cloudify_agent['distro'] = platform.dist()[0].lower()
                elif cloudify_agent['remote_execution']:
                    dist = runner.machine_distribution()
                    cloudify_agent['distro'] = dist[0].lower()

            if not cloudify_agent.get('distro_codename'):
                if cloudify_agent['local']:
                    cloudify_agent['distro_codename'] = platform.dist()[
                        2].lower()
                elif cloudify_agent['remote_execution']:
                    dist = runner.machine_distribution()
                    cloudify_agent['distro_codename'] = dist[2].lower()

            if ('distro' in cloudify_agent and
                    'distro_codename' in cloudify_agent):
                cloudify_agent['package_url'] = '{0}/packages/agents' \
                                                '/{1}-{2}-agent.tar.gz' \
                    .format(cloudify_utils.get_manager_file_server_url(),
                            cloudify_agent['distro'],
                            cloudify_agent['distro_codename'])

    if not cloudify_agent.get('basedir'):
        if cloudify_agent['local']:
            basedir = agent_utils.get_home_dir(cloudify_agent['user'])
        else:
            if cloudify_agent['windows']:
                # TODO: Get the program files directory from the machine iself
                # instead of hardcoding it an assuming it's in C:\
                basedir = 'C:\\Program Files\\Cloudify Agents'
            elif cloudify_agent['remote_execution']:
                basedir = runner.home_dir(cloudify_agent['user'])
            else:
                basedir = '~{0}'.format(cloudify_agent['user'])
        cloudify_agent['basedir'] = basedir

    directory_attributes(cloudify_agent)
