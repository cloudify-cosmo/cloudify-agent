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

import time
import threading

from cloudify import ctx
from cloudify.exceptions import NonRecoverableError
from cloudify.utils import get_agent_name
from cloudify.utils import get_manager_file_server_blueprints_root_url
from cloudify.decorators import operation

from cloudify_agent.api.plugins.installer import PluginInstaller
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.app import app
from cloudify_agent.api import utils


##########################################################################
# this array is used for creating the initial includes file of the agent
# it should contain tasks that are inside the cloudify-agent project.
##########################################################################
CLOUDIFY_AGENT_BUILT_IN_TASK_MODULES = ['cloudify_agent.operations']

import os

@operation
def install_plugins(plugins, **_):

    installer = PluginInstaller(logger=ctx.logger)

    for plugin in plugins:
        source = get_plugin_source(plugin, ctx.blueprint.id)
        args = get_plugin_args(plugin)
        ctx.logger.info('Installing plugin: {0}'.format(plugin['name']))
        package_name = installer.install(source, args)
        daemon = DaemonFactory.load(
            name=get_agent_name(),
            username=os.environ['AGENT_USERNAME'],
            storage=os.environ['AGENT_STORAGE_DIR'])
        daemon.register(package_name)


@operation
def restart(new_name=None, delay_period=5, **_):

    if new_name is None:
        new_name = utils.generate_agent_name()

    daemon = DaemonFactory.load(
        name=get_agent_name(),
        username=os.environ['AGENT_USERNAME'],
        storage=os.environ['AGENT_STORAGE_DIR'])

    # make the current master stop listening to the current queue
    # to avoid a situation where we have two masters listening on the
    # same queue.
    ctx.logger.info('Disabling current Cloudify Agent {0}'
                    .format(get_agent_name()))
    app.control.cancel_consumer(
        queue=daemon.queue,
        destination=[daemon.name]
    )
    ctx.logger.info('Cloudify Agent {0} disabled'.format(get_agent_name()))

    # clone the current daemon to preserve all the attributes
    attributes = utils.daemon_to_dict(daemon)
    ctx.logger.info('Cloned current Cloudify Agent: {0}'.format(attributes))

    # give the new daemon the new name
    attributes['name'] = new_name
    new_daemon = DaemonFactory.new(**attributes)

    # create the new daemon
    ctx.logger.info('Creating new agent: {0}'.format(new_daemon.name))
    new_daemon.create()
    ctx.logger.info('Created new agent: {0}'.format(new_daemon.name))

    # configure the new daemon
    ctx.logger.info('Configuring new agent: {0}'.format(new_daemon.name))
    new_daemon.configure()
    ctx.logger.info('Configured new agent: {0}'.format(new_daemon.name))

    ctx.logger.info('Starting new agent: {0}'.format(new_daemon.name))
    new_daemon.start()
    ctx.logger.info('Started new agent: {0}'.format(new_daemon.name))

    # start a thread that will kill the current master.
    # this is done in a thread so that the current task will not result in
    # a failure
    ctx.logger.info('Scheduling Cloudify Agent {0} for shutdown'
                    .format(get_agent_name()))
    thread = threading.Thread(target=shutdown_current_master,
                              args=[delay_period, ctx.logger])
    thread.daemon = True
    thread.start()


@operation
def stop(delay_period=5, **_):
    ctx.logger.info('Scheduling Cloudify Agent {0} for shutdown'
                    .format(get_agent_name()))
    thread = threading.Thread(target=shutdown_current_master,
                              args=[delay_period, ctx.logger])
    thread.daemon = True
    thread.start()


def shutdown_current_master(delay_period, logger):
    if delay_period > 0:
        time.sleep(delay_period)
    import os
    daemon = DaemonFactory.load(
        name=get_agent_name(),
        username=os.environ['AGENT_USERNAME'],
        storage=os.environ['AGENT_STORAGE_DIR'])
    daemon.logger = logger
    logger.info('Shutting down agent: {0}'
                .format(get_agent_name()))
    daemon.stop()


def get_plugin_args(plugin):
    args = plugin.get('install_arguments') or ''
    return args.strip()


def get_plugin_source(plugin, blueprint_id=None):

    source = plugin.get('source') or ''
    if source:
        source = source.strip()
    else:
        raise NonRecoverableError('Plugin source is not defined')

    # validate source url
    if '://' in source:
        split = source.split('://')
        schema = split[0]
        if schema not in ['http', 'https']:
            # invalid schema
            raise NonRecoverableError('Invalid schema: {0}'.format(schema))
    else:
        # Else, assume its a relative path from <blueprint_home>/plugins
        # to a directory containing the plugin archive.
        # in this case, the archived plugin is expected to reside on the
        # manager file server as a zip file.
        if blueprint_id is None:
            raise ValueError('blueprint_id must be specified when plugin '
                             'source does not contain a schema')
        blueprints_root = get_manager_file_server_blueprints_root_url()
        blueprint_plugins_url = '{0}/{1}/plugins'.format(
            blueprints_root, blueprint_id)

        source = '{0}/{1}.zip'.format(blueprint_plugins_url, source)

    return source
