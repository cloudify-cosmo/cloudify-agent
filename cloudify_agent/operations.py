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

import tempfile
import time
import threading
import ssl
import sys
import os
import copy
import json
from uuid import uuid4
from posixpath import join as urljoin
from contextlib import contextmanager

import celery
from jinja2 import Environment, FileSystemLoader

import cloudify.manager
from cloudify import ctx
from cloudify.exceptions import NonRecoverableError
from cloudify.utils import (ManagerVersion,
                            get_local_rest_certificate,
                            get_manager_file_server_url,
                            get_manager_file_server_root,
                            get_manager_rest_service_host)
from cloudify.decorators import operation

from cloudify_agent.api.plugins.installer import PluginInstaller
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.api import defaults
from cloudify_agent.api import exceptions
from cloudify_agent.api import utils
from cloudify_agent.app import app
from cloudify_agent.installer.config import configuration


@operation
def install_plugins(plugins, **_):
    installer = PluginInstaller(logger=ctx.logger)
    for plugin in plugins:
        ctx.logger.info('Installing plugin: {0}'.format(plugin['name']))
        try:
            installer.install(plugin=plugin,
                              deployment_id=ctx.deployment.id,
                              blueprint_id=ctx.blueprint.id)
        except exceptions.PluginInstallationError as e:
            # preserve traceback
            tpe, value, tb = sys.exc_info()
            raise NonRecoverableError, NonRecoverableError(str(e)), tb


@operation
def uninstall_plugins(plugins, **_):
    installer = PluginInstaller(logger=ctx.logger)
    for plugin in plugins:
        ctx.logger.info('Uninstalling plugin: {0}'.format(plugin['name']))
        if plugin.get('wagon'):
            installer.uninstall_wagon(
                package_name=plugin['package_name'],
                package_version=plugin['package_version'])
        else:
            installer.uninstall(plugin=plugin,
                                deployment_id=ctx.deployment.id)


@operation
def restart(new_name=None, delay_period=5, **_):

    cloudify_agent = ctx.instance.runtime_properties['cloudify_agent']
    if new_name is None:
        new_name = utils.internal.generate_new_agent_name(
            cloudify_agent.get('name', 'agent'))

    # update agent name in runtime properties so that the workflow will
    # what the name of the worker handling tasks to this instance.
    # the update cannot be done by setting a nested property directly
    # because they are not recognized as 'dirty'
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

    # Get the broker credentials for the daemon
    attributes.update(ctx.bootstrap_context.broker_config())

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
    daemon.before_self_stop()
    daemon.stop()


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


def create_new_agent_dict(old_agent):
    new_agent = {}
    new_agent['name'] = utils.internal.generate_new_agent_name(
        old_agent['name'])
    new_agent['remote_execution'] = True
    # TODO: broker_ip should be handled as part of fixing agent migration
    fields_to_copy = ['windows', 'ip', 'basedir', 'user',
                      'ssl_cert_path', 'agent_rest_cert_path']
    for field in fields_to_copy:
        if field in old_agent:
            new_agent[field] = old_agent[field]
    configuration.reinstallation_attributes(new_agent)
    new_agent['manager_file_server_url'] = get_manager_file_server_url()
    new_agent['old_agent_version'] = old_agent['version']
    return new_agent


@contextmanager
def _celery_client(ctx, agent):
    # We retrieve broker url from old agent in order to support
    # cases when old agent is not connected to current rabbit server.
    if 'broker_config' in agent:
        broker_config = agent['broker_config']
    else:
        broker_config = ctx.bootstrap_context.broker_config()
    broker_url = utils.internal.get_broker_url(broker_config)
    ctx.logger.info('Connecting to {0}'.format(broker_url))
    celery_client = celery.Celery()
    # We can't pass broker_url to Celery constructor because it would
    # be overriden by the value from broker_config.py.
    config = {
        'BROKER_URL': broker_url,
        'CELERY_RESULT_BACKEND': broker_url
    }
    if ManagerVersion(agent['version']) != ManagerVersion('3.2'):
        config['CELERY_TASK_RESULT_EXPIRES'] = \
            defaults.CELERY_TASK_RESULT_EXPIRES
    fd, cert_path = tempfile.mkstemp()
    os.close(fd)
    try:
        if broker_config.get('broker_ssl_enabled'):
            with open(cert_path, 'w') as cert_file:
                cert_file.write(broker_config.get('broker_ssl_cert', ''))
            broker_ssl = {
                'ca_certs': cert_path,
                'cert_reqs': ssl.CERT_REQUIRED
            }
        else:
            broker_ssl = False
        config['BROKER_USE_SSL'] = broker_ssl
        celery_client.conf.update(**config)
        yield celery_client
    finally:
        os.remove(cert_path)


def _celery_task_name(version):
    if not version or ManagerVersion(version) > ManagerVersion('3.3.1'):
        return 'cloudify.dispatch.dispatch'
    else:
        return 'script_runner.tasks.run'


def _assert_agent_alive(name, celery_client, version=None):
    tasks = utils.get_agent_registered(name, celery_client)
    if not tasks:
        raise NonRecoverableError(
            'Could not access tasks list for agent {0}'.format(name))
    task_name = _celery_task_name(version)
    if task_name not in tasks:
        raise NonRecoverableError('Task {0} is not available in agent {1}'.
                                  format(task_name, name))


def _get_manager_version():
    version_json = cloudify.manager.get_rest_client().manager.get_version()
    return ManagerVersion(version_json['version'])


def _run_install_script(old_agent, timeout, validate_only=False):
    # Assuming that if there is no version info in the agent then
    # this agent was installed by current manager.
    old_agent = copy.deepcopy(old_agent)
    if 'version' not in old_agent:
        old_agent['version'] = str(_get_manager_version())
    new_agent = create_new_agent_dict(old_agent)
    old_agent_version = new_agent['old_agent_version']

    with _celery_client(ctx, old_agent) as celery_client:
        old_agent_name = old_agent['name']
        _assert_agent_alive(old_agent_name, celery_client, old_agent_version)

        script_runner_task = 'script_runner.tasks.run'
        cloudify_context = {
            'type': 'operation',
            'task_name': script_runner_task,
            'task_target': old_agent['queue']
        }
        # Using a context manager to delete the files after sending the task
        with AgentFilesGenerator() as agent_files:
            kwargs = {'script_path': agent_files.script_url,
                      'cloudify_agent': new_agent,
                      'validate_only': validate_only,
                      '__cloudify_context': cloudify_context}
            task = _celery_task_name(old_agent_version)
            result = celery_client.send_task(
                task,
                kwargs=kwargs,
                queue=old_agent['queue']
            )
            returned_agent = result.get(timeout=timeout)

    if returned_agent['name'] != new_agent['name']:
        raise NonRecoverableError(
            'Expected agent name {0}, received {1}'.format(
                new_agent['name'], returned_agent['name'])
        )
    returned_agent.pop('old_agent_version', None)
    return {
        'old': old_agent,
        'new': returned_agent
    }


def create_agent_from_old_agent(operation_timeout=300):
    if 'cloudify_agent' not in ctx.instance.runtime_properties:
        raise NonRecoverableError(
            'cloudify_agent key not available in runtime_properties')
    if 'agent_status' not in ctx.instance.runtime_properties:
        raise NonRecoverableError(
            ('agent_status key not available in runtime_properties, '
             'validation needs to be performed before new agent installation'))
    status = ctx.instance.runtime_properties['agent_status']
    if not status['agent_alive_crossbroker']:
        raise NonRecoverableError(
            ('Last validation attempt has shown that agent is dead. '
             'Rerun validation.'))
    old_agent = ctx.instance.runtime_properties['cloudify_agent']
    agents = _run_install_script(old_agent,
                                 operation_timeout,
                                 validate_only=False)
    # Make sure that new celery agent was started:
    returned_agent = agents['new']
    ctx.logger.info('Installed agent {0}'.format(returned_agent['name']))
    _assert_agent_alive(returned_agent['name'], app)
    # Setting old_cloudify_agent in order to uninstall it later.
    ctx.instance.runtime_properties['old_cloudify_agent'] = agents['old']
    ctx.instance.runtime_properties['cloudify_agent'] = returned_agent


@operation
def create_agent_amqp(install_agent_timeout, **_):
    create_agent_from_old_agent(install_agent_timeout)


@operation
def validate_agent_amqp(validate_agent_timeout, fail_on_agent_dead=False,
                        fail_on_agent_not_installable=False, **_):
    if 'cloudify_agent' not in ctx.instance.runtime_properties:
        raise NonRecoverableError(
            'cloudify_agent key not available in runtime_properties')
    agent = ctx.instance.runtime_properties['cloudify_agent']
    agent_name = agent['name']
    result = {}
    ctx.logger.info(('Checking if agent can be accessed through '
                     'current rabbitmq'))
    try:
        _assert_agent_alive(agent_name, app)
    except Exception as e:
        result['agent_alive'] = False
        result['agent_alive_error'] = str(e)
        ctx.logger.info('Agent unavailable, reason {0}'.format(str(e)))
    else:
        result['agent_alive'] = True
    ctx.logger.info(('Checking if agent can be accessed through '
                     'different rabbitmq'))
    try:
        _run_install_script(agent, validate_agent_timeout, validate_only=True)
    except Exception as e:
        result['agent_alive_crossbroker'] = False
        result['agent_alive_crossbroker_error'] = str(e)
        ctx.logger.info('Agent unavailable, reason {0}'.format(str(e)))
    else:
        result['agent_alive_crossbroker'] = True
    result['timestamp'] = time.time()
    ctx.instance.runtime_properties['agent_status'] = result
    if fail_on_agent_dead and not result['agent_alive']:
        raise NonRecoverableError(result['agent_alive_error'])
    if fail_on_agent_not_installable and not result[
            'agent_alive_crossbroker']:
        raise NonRecoverableError(result['agent_alive_crossbroker_error'])


class AgentFilesGenerator(object):
    def __init__(self):
        self._unique_id = uuid4()
        self._script_filename = '{0}_install_agent.py'.format(self._unique_id)
        self._creds_filename = '{0}_creds.json'.format(self._unique_id)
        self._file_server_root = get_manager_file_server_root()
        self._script_path = self._get_file_path(self._script_filename)
        self._creds_path = self._get_file_path(self._creds_filename)
        self.script_url = self._get_script_url()
        self._creds_url = self._get_creds_url()

    def __enter__(self):
        self._generate_files()
        return self

    def _generate_files(self):
        creds_json_content = self._get_creds_json_content()
        script_content = self._get_rendered_script()

        self._write_file(self._script_path, script_content)
        self._write_file(self._creds_path, creds_json_content)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._delete_file(self._script_path)
        self._delete_file(self._creds_path)

    @staticmethod
    def _delete_file(file_path):
        try:
            os.remove(file_path)
        except IOError:
            pass

    @staticmethod
    def _write_file(file_path, content):
        with open(file_path, 'w') as f:
            f.write(content)

    def _get_file_path(self, filename):
        return os.path.join(
            self._file_server_root,
            'cloudify_agent',
            filename
        )

    def _get_script_url(self):
        # We specifically need a non-HTTPS URL in order to download the script
        rest_host = 'http://{0}/'.format(get_manager_rest_service_host())
        return urljoin(
            rest_host,
            'resources',
            'cloudify_agent',
            self._script_filename
        )

    def _get_rendered_script(self):
        """Render the install_agent script with the credentials file URL
        """
        cloudify_dir_path = os.path.join(self._file_server_root, 'cloudify')
        template_env = Environment(loader=FileSystemLoader(cloudify_dir_path))
        template = template_env.get_template('install_agent_template.py')
        return template.render(creds_url=self._creds_url)

    def _get_creds_url(self):
        return urljoin(
            get_manager_file_server_url(),
            'cloudify_agent',
            self._creds_filename
        )

    @staticmethod
    def _get_creds_json_content():
        with open(get_local_rest_certificate(), 'r') as cert_file:
            ssl_cert_content = cert_file.read()

        return json.dumps({
            'ssl_cert_content': ssl_cert_content,
            'rest_token': ctx.rest_token
        })
