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
import getpass
import platform
from functools import wraps

from cloudify import ctx
from cloudify import utils
from cloudify import context

from cloudify_agent.installer import exceptions


def cloudify_agent_property(agent_property=None,
                            context_attribute=None,
                            mandatory=True):

    if context_attribute is None:
        context_attribute = agent_property

    def decorator(function):

        @wraps(function)
        def wrapper(*args, **kwargs):

            invocation = args[0]
            node_properties = ctx.node.properties['cloudify_agent']
            agent_context = ctx.bootstrap_context.cloudify_agent
            runtime_properties = ctx.instance.runtime_properties.get(
                'cloudify_agent', {})

            # if the property was given in the invocation, use it.
            if agent_property in invocation:
                return

            # if the property is inside a runtime property, use it.
            if agent_property in runtime_properties:
                invocation[agent_property] = runtime_properties[
                    agent_property]
                return

            # if the property is declared on the node, use it
            if agent_property in node_properties:
                invocation[agent_property] = node_properties[agent_property]
                return

            # if the property is inside the bootstrap context,
            # and its value is not None, use it
            if hasattr(agent_context, context_attribute):
                value = getattr(agent_context, context_attribute)
                if value is not None:
                    invocation[agent_property] = getattr(agent_context,
                                                         context_attribute)
                    return

            value = function(*args, **kwargs)
            if value is not None:
                invocation[agent_property] = value

            # if there is no value, and the property is mandatory
            if agent_property not in invocation and mandatory:
                inputs_path = '{0}.interfaces.[{1}].inputs.cloudify_agent'\
                    .format(ctx.node.name, ctx.task_name)
                properties_path = '{0}.properties.cloudify_agent'.format(
                    ctx.node.name
                )
                runtime_properties_path = \
                    '{0}.runtime_properties.cloudify_agent'\
                    .format(ctx.instance.id)
                context_path = 'bootstrap_context.cloudify_agent'
                raise exceptions.AgentInstallerConfigurationError(
                    '{0} was not found in any of '
                    'the following: 1. {1}; 2. {2}; 3. {3}; 4. {4}'
                    .format(agent_property,
                            inputs_path,
                            runtime_properties_path,
                            properties_path,
                            context_path)
                )

        return wrapper

    return decorator


def prepare_connection(cloudify_agent):

    """
    Augments the cloudify agent connection properties with values according to
    heuristics determined in the cloudify_agent_property decorator.

    :param cloudify_agent: the agent properties

    """

    _set_user(cloudify_agent)
    _set_key(cloudify_agent)
    _set_password(cloudify_agent)
    _set_port(cloudify_agent)
    _set_ip(cloudify_agent)
    _set_local(cloudify_agent)
    _set_windows(cloudify_agent)
    _set_connection_retry_interval(cloudify_agent)


def prepare_agent(cloudify_agent):

    """
    Augments the cloudify agent properties with values according to heuristics
    determined in the cloudify_agent_property decorator.

    :param cloudify_agent: the agent properties

    """

    ##################################################################
    # the order of each setter invocation is very important because
    # some properties rely on other, do not change the order unless you
    # know exactly what you are doing
    ##################################################################

    _set_queue(cloudify_agent)
    _set_name(cloudify_agent)
    _set_basedir(cloudify_agent)
    _set_min_workers(cloudify_agent)
    _set_max_workers(cloudify_agent)
    _set_distro(cloudify_agent)
    _set_distro_codename(cloudify_agent)
    _set_manager_ip(cloudify_agent)
    _set_env(cloudify_agent)
    _set_agent_dir(cloudify_agent)
    _set_workdir(cloudify_agent)
    _set_envdir(cloudify_agent)
    _set_process_management(cloudify_agent)
    _set_source_url(cloudify_agent)
    _set_requirements(cloudify_agent)
    _set_package_url(cloudify_agent)
    _set_fabric_env(cloudify_agent)
    _set_disable_requiretty(cloudify_agent)

    def validate():
        if 'source_url' in cloudify_agent and 'package_url' in cloudify_agent:
            raise exceptions.AgentInstallerConfigurationError(
                "Cannot specify both 'source_url' and 'package_url' "
                "simultaneously."
            )
        if 'source_url' not in cloudify_agent and 'package_url' not in \
                cloudify_agent:
            raise exceptions.AgentInstallerConfigurationError(
                "Must specify either 'source_url' or 'package_url'"
            )

    validate()


########################################################################
# These are properties that are passed to the FabricRunner in order to
# either connect to the remote machine or just run local commands.
# they must be calculated here.
########################################################################

@cloudify_agent_property(
    agent_property='port',
    context_attribute='remote_execution_port',
    mandatory=False
)
def _set_port(_):
    pass


@cloudify_agent_property('user', mandatory=False)
def _set_user(_):
    return getpass.getuser()


@cloudify_agent_property(
    agent_property='key',
    context_attribute='agent_key_path',
    mandatory=False
)
def _set_key(_):
    pass


@cloudify_agent_property('password', mandatory=False)
def _set_password(_):
    pass


@cloudify_agent_property('local')
def _set_local(_):
    return ctx.type == context.DEPLOYMENT


@cloudify_agent_property('windows')
def _set_windows(cloudify_agent):
    if cloudify_agent['local']:
        # auto detect
        return os.name == 'nt'
    else:
        # default to False with remote cases
        # this property should be set in the blueprint
        # do install on windows machines remotely
        return False


@cloudify_agent_property('connection_retry_interval')
def _set_connection_retry_interval(_):
    return 5

########################################################################
# These are properties that are essential for the installer to operate,
# they either do not have defaults on the agent side or simply are not
# related to the agent side. (like distro, basedir...)
########################################################################


@cloudify_agent_property('process_management')
def _set_process_management(cloudify_agent):
    if cloudify_agent['windows']:
        return {'name': 'nssm'}
    else:
        return {'name': 'init.d'}


@cloudify_agent_property('distro', mandatory=False)
def _set_distro(cloudify_agent):
    if cloudify_agent['windows']:
        return
    if cloudify_agent['local']:
        return platform.dist()[0].lower()
    dist = ctx.installer.runner.machine_distribution()
    return dist[0].lower()


@cloudify_agent_property('distro_codename', mandatory=False)
def _set_distro_codename(cloudify_agent):
    if cloudify_agent['windows']:
        return
    if cloudify_agent['local']:
        return platform.dist()[2].lower()
    dist = ctx.installer.runner.machine_distribution()
    return dist[2].lower()


@cloudify_agent_property('package_url', mandatory=False)
def _set_package_url(cloudify_agent):
    if 'source_url' in cloudify_agent:
        return
    return '{0}/packages/agents/{1}-{2}-agent.tar.gz'.format(
        utils.get_manager_file_server_url(),
        cloudify_agent['distro'],
        cloudify_agent['distro_codename']
    )


@cloudify_agent_property('source_url', mandatory=False)
def _set_source_url(_):
    pass


@cloudify_agent_property('disable_requiretty')
def _set_disable_requiretty(_):
    return True


@cloudify_agent_property('requirements', mandatory=False)
def _set_requirements(_):
    pass


@cloudify_agent_property('ip')
def _set_ip(_):
    ip = None
    if ctx.node.properties.get('ip'):
        ip = ctx.node.properties['ip']
    if ctx.instance.runtime_properties.get('ip'):
        ip = ctx.instance.runtime_properties['ip']
    return ip


@cloudify_agent_property('basedir')
def _set_basedir(cloudify_agent):

    # the default will be the home directory
    if cloudify_agent['local']:
        return utils.get_home_dir(cloudify_agent['user'])
    else:
        return ctx.installer.runner.home_dir(cloudify_agent['user'])


@cloudify_agent_property('agent_dir')
def _set_agent_dir(cloudify_agent):
    name = cloudify_agent['name']
    basedir = cloudify_agent['basedir']
    if cloudify_agent['windows']:
        return '{0}\\{1}'.format(basedir, name)
    else:
        return os.path.join(basedir, name)


@cloudify_agent_property('workdir')
def _set_workdir(cloudify_agent):
    agent_dir = cloudify_agent['agent_dir']
    if cloudify_agent['windows']:
        return '{0}\\{1}'.format(agent_dir, 'work')
    else:
        return os.path.join(agent_dir, 'work')


@cloudify_agent_property('name')
def _set_name(cloudify_agent):
    return cloudify_agent['queue']


@cloudify_agent_property('queue')
def _set_queue(cloudify_agent):
    if ctx.type == context.DEPLOYMENT:
        workflows_worker = cloudify_agent.get('workflows_worker', False)
        suffix = '_workflows' if workflows_worker else ''
        queue = '{0}{1}'.format(ctx.deployment.id, suffix)
    else:
        queue = ctx.instance.id
    return queue


@cloudify_agent_property('manager_ip')
def _set_manager_ip(_):
    return utils.get_manager_ip()


@cloudify_agent_property('env', mandatory=False)
def _set_env(_):
    return {}


@cloudify_agent_property('fabric_env', mandatory=False)
def _set_fabric_env(_):
    return {}


########################################################################
# These are properties that are passed directly to the cfy-agent
# command line. they have default on the agent. That is why we don't
# specify them here again. However, for these properties to be configurable
# from the blueprint, these setters must defined here.
########################################################################


@cloudify_agent_property('min_workers', mandatory=False)
def _set_min_workers(_):
    pass


@cloudify_agent_property('max_workers', mandatory=False)
def _set_max_workers(_):
    pass


#############################################################################
# This isn't exposed as a property because the env directory is tied to the
# way we package the agent, and therefore cannot be an arbitrary path.
# this setting is just for internal use and convenience later on.
#############################################################################


def _set_envdir(cloudify_agent):
    agent_dir = cloudify_agent['agent_dir']
    if cloudify_agent['windows']:
        envdir = '{0}\\{1}'.format(agent_dir, 'env')
    else:
        envdir = os.path.join(agent_dir, 'env')
    cloudify_agent['envdir'] = envdir
