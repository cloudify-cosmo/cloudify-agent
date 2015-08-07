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

import uuid
import time
import threading
import sys
import os
import copy

import celery

from cloudify import ctx
from cloudify.exceptions import NonRecoverableError
from cloudify.utils import get_manager_file_server_blueprints_root_url
from cloudify.decorators import operation, workflow

from cloudify_rest_client.client import DEFAULT_API_VERSION

from cloudify_agent.api.plugins.installer import PluginInstaller
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.api import defaults
from cloudify_agent.api import exceptions
from cloudify_agent.api import utils
from cloudify_agent.app import app

from cloudify_agent.installer.config import configuration

##########################################################################
# this array is used for creating the initial includes file of the agent
# it should contain tasks that are inside the cloudify-agent project.
##########################################################################
CLOUDIFY_AGENT_BUILT_IN_TASK_MODULES = [
    'cloudify.plugins.workflows',
    'cloudify_agent.operations',
    'cloudify_agent.installer.operations',

    # maintain backwards compatibility with version < 3.3
    'worker_installer.tasks',
    'windows_agent_installer.tasks',
    'plugin_installer.tasks',
    'windows_plugin_installer.tasks'
]


def _install_plugins(plugins):
    installer = PluginInstaller(logger=ctx.logger)
    for plugin in plugins:
        source = get_plugin_source(plugin, ctx.blueprint.id)
        args = get_plugin_args(plugin)
        ctx.logger.info('Installing plugin: {0}'.format(plugin['name']))
        try:
            package_name = installer.install(source, args)
        except exceptions.PluginInstallationError as e:
            # preserve traceback
            tpe, value, tb = sys.exc_info()
            raise NonRecoverableError, NonRecoverableError(str(e)), tb

        daemon = _load_daemon(logger=ctx.logger)
        daemon.register(package_name)
        _save_daemon(daemon)


@operation
def install_plugins(plugins, **_):
    _install_plugins(plugins)


@operation
def restart(new_name=None, delay_period=5, **_):

    if new_name is None:
        new_name = utils.internal.generate_agent_name()

    # update agent name in runtime properties so that the workflow will
    # what the name of the worker handling tasks to this instance.
    # the update cannot be done by setting a nested property directly
    # because they are not recognized as 'dirty'
    cloudify_agent = ctx.instance.runtime_properties['cloudify_agent']
    cloudify_agent['name'] = new_name
    ctx.instance.runtime_properties['cloudify_agent'] = cloudify_agent

    # must update instance here because the process may shutdown before
    # the decorator has a chance to do it.
    ctx.instance.update()

    daemon = _load_daemon(logger=ctx.logger)

    # make the current master stop listening to the current queue
    # to avoid a situation where we have two masters listening on the
    # same queue.
    app.control.cancel_consumer(
        queue=daemon.queue,
        destination=['celery@{0}'.format(daemon.name)]
    )

    # clone the current daemon to preserve all the attributes
    attributes = utils.internal.daemon_to_dict(daemon)

    # give the new daemon the new name
    attributes['name'] = new_name

    # remove the log file and pid file so that new ones will be created
    # for the new agent
    del attributes['log_file']
    del attributes['pid_file']

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
        username=utils.internal.get_daemon_user(),
        storage=utils.internal.get_daemon_storage_dir())
    return factory.load(utils.internal.get_daemon_name(), logger=logger)


def _save_daemon(daemon):
    factory = DaemonFactory(
        username=utils.internal.get_daemon_user(),
        storage=utils.internal.get_daemon_storage_dir())
    factory.save(daemon)


def _get_broker_url(agent):
    if 'broker_url' in agent:
        return agent['broker_url']
    broker_port = agent.get('broker_port', defaults.BROKER_PORT)
    broker_ip = agent.get('broker_ip', agent['manager_ip'])
    return defaults.BROKER_URL.format(broker_ip,
                                      broker_port)


def create_new_agent_dict(old_agent, suffix=None):
    if suffix is None:
        suffix = str(uuid.uuid4())
    new_agent = copy.deepcopy(old_agent)
    fields_to_delete = ['name', 'queue', 'workdir', 'agent_dir', 'envdir',
                        'manager_ip', 'package_url', 'source_url'
                        'manager_port', 'broker_url', 'broker_port',
                        'broker_ip', 'key']
    for field in fields_to_delete:
        if field in new_agent:
            del(new_agent[field])
    new_agent['name'] = '{0}_{1}'.format(old_agent['name'], suffix)
    configuration.reinstallation_attributes(new_agent)
    new_agent['broker_url'] = _get_broker_url(new_agent)
    return new_agent


def create_agent_from_old_agent():
    if 'cloudify_agent' not in ctx.instance.runtime_properties:
        raise NonRecoverableError(
            'cloudify_agent key not available in runtime_properties')
    old_agent = ctx.instance.runtime_properties['cloudify_agent']
    new_agent = create_new_agent_dict(old_agent)
    ctx.instance.runtime_properties['new_cloudify_agent'] = new_agent
    ctx.instance.update()
    # We retrieve broker url from old agent in order to support
    # cases when old agent is not connected to current rabbit server.
    broker_url = _get_broker_url(old_agent)
    env_broker_url = os.environ.get('CELERY_BROKER_URL')
    os.environ['CELERY_BROKER_URL'] = broker_url
    try:
        celery_client = celery.Celery(broker=broker_url, backend=broker_url)
        # This one will have to be modified for 3.2
        app_conf = {
            'CELERY_TASK_RESULT_EXPIRES': defaults.CELERY_TASK_RESULT_EXPIRES
        }
        celery_client.conf.update(**app_conf)
        script_format = 'http://{0}/api/{1}/node-instances/{2}/install_agent.py'
        script_url = script_format.format(
            new_agent['manager_ip'],
            DEFAULT_API_VERSION,
            ctx.instance.id
        )
        result = celery_client.send_task(
            'script_runner.tasks.run',
            args=[script_url],
            queue=old_agent['queue']
        )
        timeout = 2 * 60
        result.get(timeout=timeout)
    finally:
        if env_broker_url is None:
            del(os.environ['CELERY_BROKER_URL'])
        else:
            os.environ['CELERY_BROKER_URL'] = env_broker_url
    # Make sure that new celery agent was started:
    agent_status = app.control.inspect(destination=[
        'celery@{0}'.format(new_agent['name'])])
    if not agent_status.active():
        raise NonRecoverableError('Could not start agent.')
    # Setting old_cloudify_agent in order to uninstall it later.
    ctx.instance.runtime_properties['old_cloudify_agent'] = old_agent
    ctx.instance.runtime_properties['cloudify_agent'] = new_agent
    del(ctx.instance.runtime_properties['new_cloudify_agent'])


@operation
def create_agent_amqp(**_):
    create_agent_from_old_agent()
