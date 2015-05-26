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
from cloudify.utils import get_manager_file_server_blueprints_root_url
from cloudify.utils import get_daemon_name
from cloudify.utils import get_daemon_storage_dir
from cloudify.utils import get_daemon_user
from cloudify.decorators import operation

from cloudify_agent.api.plugins.installer import PluginInstaller
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.api import utils
from cloudify_agent.app import app


##########################################################################
# this array is used for creating the initial includes file of the agent
# it should contain tasks that are inside the cloudify-agent project.
##########################################################################
CLOUDIFY_AGENT_BUILT_IN_TASK_MODULES = [
    'cloudify_agent.operations',
    'cloudify_agent.installer.operations'
]


@operation
def install_plugins(plugins, **_):

    installer = PluginInstaller(logger=ctx.logger)

    for plugin in plugins:
        source = get_plugin_source(plugin, ctx.blueprint.id)
        args = get_plugin_args(plugin)
        ctx.logger.info('Installing plugin: {0}'.format(plugin['name']))
        package_name = installer.install(source, args)
        daemon = _load_daemon(logger=ctx.logger)
        daemon.register(package_name)
        _save_daemon(daemon)


@operation
def restart(new_name=None, delay_period=5, **_):

    if new_name is None:
        new_name = utils.generate_agent_name()

    # update agent name in runtime properties so that the workflow will
    # what the name of the worker handling tasks to this instance.
    ctx.logger.info('Current runtime: {0}'.format(
        ctx.instance.runtime_properties['cloudify_agent']))
    ctx.logger.info('Setting cloudify_agent.name to {0}'.format(new_name))
    ctx.instance.runtime_properties['cloudify_agent']['name'] = new_name

    daemon = _load_daemon(logger=ctx.logger)

    # make the current master stop listening to the current queue
    # to avoid a situation where we have two masters listening on the
    # same queue.
    app.control.cancel_consumer(
        queue=daemon.queue,
        destination=[daemon.name]
    )

    # clone the current daemon to preserve all the attributes
    attributes = utils.daemon_to_dict(daemon)

    # give the new daemon the new name
    attributes['name'] = new_name
    new_daemon = DaemonFactory().new(logger=ctx.logger, **attributes)

    # create the new daemon
    new_daemon.create()
    _save_daemon(new_daemon)

    # configure the new daemon
    new_daemon.configure()
    new_daemon.start()

    # start a thread that will kill the current master.
    # this is done in a thread so that the current task will not result in
    # a failure
    thread = threading.Thread(target=shutdown_current_master,
                              args=[delay_period, ctx.logger])
    thread.daemon = True
    thread.start()


@operation
def stop(delay_period=5, **_):
    thread = threading.Thread(target=shutdown_current_master,
                              args=[delay_period, ctx.logger])
    thread.daemon = True
    thread.start()


def shutdown_current_master(delay_period, logger):
    if delay_period > 0:
        time.sleep(delay_period)
    daemon = _load_daemon(logger=logger)
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


def _load_daemon(logger):
    factory = DaemonFactory(
        username=get_daemon_user(),
        storage=get_daemon_storage_dir())
    return factory.load(get_daemon_name(), logger=logger)


def _save_daemon(daemon):
    factory = DaemonFactory(
        username=get_daemon_user(),
        storage=get_daemon_storage_dir())
    factory.save(daemon)
