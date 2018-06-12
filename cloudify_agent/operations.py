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
import sys
import os
import copy
from posixpath import join as urljoin
from contextlib import contextmanager

import cloudify.manager
from cloudify import amqp_client, ctx
from cloudify.constants import BROKER_PORT_SSL
from cloudify.broker_config import broker_hostname
from cloudify.exceptions import NonRecoverableError, RecoverableError
from cloudify.utils import (get_tenant,
                            ManagerVersion,
                            get_local_rest_certificate)
from cloudify.decorators import operation
from cloudify.error_handling import deserialize_known_exception

from cloudify_agent.celery_app import get_celery_app
from cloudify_agent.api.plugins.installer import PluginInstaller
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.api import exceptions
from cloudify_agent.api import utils
from cloudify_agent.installer.script import \
    init_script_download_link, cleanup_scripts
from cloudify_agent.installer.config.agent_config import CloudifyAgentConfig
from cloudify_agent.installer.config.agent_config import \
    update_agent_runtime_properties

CELERY_TASK_RESULT_EXPIRES = 600


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
    update_agent_runtime_properties(cloudify_agent)

    daemon = _load_daemon(logger=ctx.logger)

    # make the current master stop listening to the current queue
    # to avoid a situation where we have two masters listening on the
    # same queue.
    rest_tenant = get_tenant()
    app = get_celery_app(tenant=rest_tenant)
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


def _set_default_new_agent_config_values(old_agent, new_agent):
    new_agent['name'] = utils.internal.generate_new_agent_name(
        old_agent['name']
    )
    # Set the broker IP explicitly to the current manager's IP
    new_agent['broker_ip'] = broker_hostname
    new_agent['old_agent_version'] = old_agent['version']
    new_agent['disable_requiretty'] = False
    new_agent['install_with_sudo'] = True
    new_agent['networks'] = ctx.bootstrap_context.cloudify_agent.networks
    new_agent['cluster'] = ctx.bootstrap_context.cloudify_agent.cluster or []


def _copy_values_from_old_agent_config(old_agent, new_agent):
    fields_to_copy = ['windows', 'ip', 'basedir', 'user', 'distro_codename',
                      'distro', 'broker_ssl_cert_path', 'agent_rest_cert_path',
                      'network', 'local', 'install_method',
                      'process_management']
    for field in fields_to_copy:
        if field in old_agent:
            new_agent[field] = old_agent[field]


def create_new_agent_config(old_agent):
    new_agent = CloudifyAgentConfig()
    _set_default_new_agent_config_values(old_agent, new_agent)
    _copy_values_from_old_agent_config(old_agent, new_agent)
    new_agent.set_default_values()
    new_agent.set_installation_params(runner=None)
    return new_agent


@contextmanager
def _celery_app(agent):
    # We retrieve broker url from old agent in order to support
    # cases when old agent is not connected to current rabbit server.
    broker_config = agent.get('broker_config',
                              ctx.bootstrap_context.broker_config())
    agent_version = agent.get('version') or str(_get_manager_version())
    broker_url = utils.internal.get_broker_url(broker_config)
    ssl_cert_path = _get_ssl_cert_path(broker_config)
    celery_client = get_celery_app(
        broker_url=broker_url,
        broker_ssl_enabled=broker_config.get('broker_ssl_enabled'),
        broker_ssl_cert_path=ssl_cert_path
    )
    if ManagerVersion(agent_version) != ManagerVersion('3.2'):
        celery_client.conf['CELERY_TASK_RESULT_EXPIRES'] = \
            CELERY_TASK_RESULT_EXPIRES
    try:
        yield celery_client
    finally:
        if ssl_cert_path:
            os.remove(ssl_cert_path)


def _get_ssl_cert_path(broker_config):
    if broker_config.get('broker_ssl_enabled'):
        fd, ssl_cert_path = tempfile.mkstemp()
        os.close(fd)
        with open(ssl_cert_path, 'w') as cert_file:
            cert_file.write(broker_config.get('broker_ssl_cert', ''))
        return ssl_cert_path
    else:
        return None


def _get_ssl_cert_content(old_agent_version):
    if ManagerVersion(old_agent_version) < ManagerVersion('4.2'):
        return None

    with open(get_local_rest_certificate(), 'r') as cert_file:
        return cert_file.read()


def _celery_task_name(version):
    if not version or ManagerVersion(version) > ManagerVersion('3.3.1'):
        return 'cloudify.dispatch.dispatch'
    else:
        return 'script_runner.tasks.run'


def _get_manager_version():
    version_json = cloudify.manager.get_rest_client().manager.get_version()
    return ManagerVersion(version_json['version'])


def _http_rest_host(cloudify_agent):
    return 'http://{0}/'.format(cloudify_agent['rest_host'])


def _get_init_script_path_and_url(new_agent, old_agent_version):
    script_path, script_url = init_script_download_link(new_agent)
    # Prior to 4.2 (and script plugin 1.5.1) there was no way to pass
    # a certificate to the script plugin, so the initial script must be
    # passed over http
    if ManagerVersion(old_agent_version) < ManagerVersion('4.2'):
        # This is the relative path on the manager, except the host and port
        link_relpath = script_url.split('/', 3)[3]
        script_url = urljoin(_http_rest_host(new_agent), link_relpath)

    return script_path, script_url


def _validate_created_agent(new_agent):
    created_agent = ctx.instance.runtime_properties['cloudify_agent']
    if created_agent['name'] != new_agent['name']:
        raise NonRecoverableError(
            'Expected agent name {0}, received {1}'.format(
                new_agent['name'], created_agent['name'])
        )
    created_agent.pop('old_agent_version', None)
    created_agent.pop('broker_config', None)
    return created_agent


def _get_cloudify_context(agent, task_name):
    """
    Return the cloudify context that would be set in tasks sent to the old
    agent
    """
    return {
        '__cloudify_context': {
            'type': 'operation',
            'task_name': task_name,
            'task_target': agent['queue'],
            'node_id': ctx.instance.id,
            'workflow_id': ctx.workflow_id,
            'execution_id': ctx.execution_id,
            'tenant': ctx.tenant,
            'rest_token': agent['rest_token']
        }
    }


def _build_install_script_params(agent, script_url):
    kwargs = _get_cloudify_context(
        agent=agent,
        task_name='script_runner.tasks.run'
    )
    kwargs['script_path'] = script_url
    kwargs['ssl_cert_content'] = _get_ssl_cert_content(agent['version'])
    return kwargs


def _send_celery_task(agent, params, timeout):
    with _celery_app(agent) as celery_app:
        if not _validate_celery(agent):
            raise RecoverableError('Agent is not responding')
        task = _celery_task_name(agent['version'])
        result = celery_app.send_task(
            task,
            kwargs=params,
            queue=agent['queue']
        )
        result.get(timeout=timeout)


@contextmanager
def _get_amqp_client(agent):
    delete_cert_path = False
    if agent.get('broker_config'):
        broker_config = agent['broker_config']
        ssl_cert_path = _get_ssl_cert_path(broker_config)
        # Using a temp path, so we need to delete it
        delete_cert_path = True
    else:
        broker_config = _get_broker_config(agent)
        ssl_cert_path = get_local_rest_certificate()

    tenant = get_tenant()
    try:
        yield amqp_client.get_client(
            amqp_host=broker_config.get('broker_ip'),
            amqp_user=tenant.get('rabbitmq_username'),
            amqp_port=broker_config.get('broker_port'),
            amqp_pass=tenant.get('rabbitmq_password'),
            amqp_vhost=tenant.get('rabbitmq_vhost'),
            ssl_enabled=broker_config.get('broker_ssl_enabled'),
            ssl_cert_path=ssl_cert_path
        )
    finally:
        if delete_cert_path and ssl_cert_path:
            os.remove(ssl_cert_path)


def _send_amqp_task(agent, params, timeout):
    if not _validate_cloudify_amqp(agent):
        raise RecoverableError('Agent is not responding')

    task = {'cloudify_task': {'kwargs': params}}
    handler = amqp_client.BlockingRequestResponseHandler(
        exchange=agent['queue'])

    with _get_amqp_client(agent) as client:
        client.add_handler(handler)
        with client:
            result = handler.publish(task, routing_key='operation',
                                     timeout=timeout)
    error = result.get('error')
    if error:
        raise deserialize_known_exception(error)


def _send_task(agent, params, timeout):
    if _uses_cloudify_amqp(agent):
        _send_amqp_task(agent, params, timeout)
    else:
        _send_celery_task(agent, params, timeout)


def _run_script(agent, script_url, timeout):
    params = _build_install_script_params(agent, script_url)

    try:
        _send_task(agent, params, timeout)
    finally:
        cleanup_scripts()


def _run_install_script(old_agent, timeout):
    old_agent = copy.deepcopy(old_agent)
    if 'version' not in old_agent:
        # Assuming that if there is no version info in the agent then
        # this agent was installed by current manager.
        old_agent['version'] = str(_get_manager_version())
    new_agent = create_new_agent_config(old_agent)
    _, script_url = _get_init_script_path_and_url(
        new_agent, old_agent['version']
    )

    _run_script(old_agent, script_url, timeout)

    created_agent = _validate_created_agent(new_agent)
    return {'old': old_agent, 'new': created_agent}


def _stop_old_agent_and_diamond(old_agent, timeout):
    stop_monitoring_params = _get_cloudify_context(
        queue=old_agent['queue'],
        task_name='diamond_agent.tasks.stop'
    )
    stop_agent_params = _get_cloudify_context(
        queue=old_agent['queue'],
        task_name='cloudify_agent.operations.stop'
    )

    _send_task(old_agent, stop_monitoring_params, timeout)
    _send_task(old_agent, stop_agent_params, timeout)


def _validate_agent():
    if 'cloudify_agent' not in ctx.instance.runtime_properties:
        raise NonRecoverableError(
            'cloudify_agent key not available in runtime_properties')
    agent = ctx.instance.runtime_properties['cloudify_agent']
    if 'broker_config' not in agent:
        raise NonRecoverableError(
            'broker_config key not available in cloudify_agent'
        )
    if 'agent_status' not in ctx.instance.runtime_properties:
        raise NonRecoverableError(
            ('agent_status key not available in runtime_properties, '
             'validation needs to be performed before '
             'new agent installation'))
    status = ctx.instance.runtime_properties['agent_status']
    if not status['agent_alive_crossbroker']:
        raise NonRecoverableError(
            ('Last validation attempt has shown that agent is dead. '
             'Rerun validation.'))
    return agent


@operation
def create_agent_amqp(install_agent_timeout=300, manager_ip=None,
                      manager_certificate=None, stop_old_agent=False, **_):
    """
    Installs a new agent on a host machine.
    :param install_agent_timeout: operation's timeout.
    :param manager_ip: the private IP of the current leader (master) Manager.
     This IP is used to connect to the Manager's RabbitMQ.
     (relevant only in HA cluster)
    :param manager_certificate: the SSL certificate of the current leader
    (master) Manager. (relevant only in HA cluster)
    :param stop_old_agent: if set, stop the old agent after successfully
    installing the new one
    """
    old_agent = _validate_agent()
    _update_broker_config(old_agent, manager_ip, manager_certificate)
    agents = _run_install_script(old_agent, install_agent_timeout)
    new_agent = agents['new']
    ctx.logger.info('Installed agent {0}'.format(new_agent['name']))

    result = _validate_current_amqp(new_agent)
    if not result['agent_alive']:
        raise RecoverableError('New agent did not start and connect')

    if stop_old_agent:
        _stop_old_agent_and_diamond(old_agent, install_agent_timeout)

    # Setting old_cloudify_agent in order to uninstall it later.
    ctx.instance.runtime_properties['old_cloudify_agent'] = agents['old']
    update_agent_runtime_properties(new_agent)


def _validate_celery(agent):
    agent_name = agent['name']
    agent_version = agent.get('version')
    with _celery_app(agent) as celery_app:
        broker_url = _conceal_amqp_password(celery_app.conf['BROKER_URL'])
        ctx.logger.info(
            'Checking if agent can be accessed through celery: {0}'
            .format(broker_url))
        tasks = utils.get_agent_registered(agent_name, celery_app)
        # Using RecoverableError to allow retries
        if not tasks:
            raise RecoverableError(
                'Could not access tasks list for agent {0}'.format(agent_name))
        task_name = _celery_task_name(agent_version)
        if task_name not in tasks:
            raise RecoverableError('Task {0} is not available in agent {1}'.
                                   format(task_name, agent_name))
        return True


def _validate_cloudify_amqp(agent):
    with _get_amqp_client(agent) as client:
        return utils.is_agent_alive(agent['name'], client)


def _uses_cloudify_amqp(agent):
    version = agent.get('version')
    return version and ManagerVersion(version) >= ManagerVersion('4.4')


def _validate_old_amqp(agent):
    validator = _validate_cloudify_amqp if _uses_cloudify_amqp(agent) \
        else _validate_celery
    try:
        ctx.logger.info('Trying old AMQP...')
        is_alive = validator(agent)
    except Exception as e:
        display_err = str(e)
        ctx.logger.info('Agent unavailable, reason {0}'.format(display_err))
        is_alive = False
    else:
        display_err = ''

    return {
        'agent_alive_crossbroker': is_alive,
        'agent_alive_crossbroker_error': display_err
    }


def _validate_current_amqp(agent):
    try:
        ctx.logger.info('Trying current AMQP...')
        is_alive = _validate_cloudify_amqp(agent)
    # Using RecoverableError to allow retries
    except RecoverableError:
        raise
    except Exception as e:
        display_err = str(e)
        ctx.logger.info('Agent unavailable, reason {0}'.format(display_err))
        is_alive = False
    else:
        display_err = ''

    return {
        'agent_alive': is_alive,
        'agent_alive_error': display_err
    }


@operation
def validate_agent_amqp(current_amqp=True, manager_ip=None,
                        manager_certificate=None, **_):
    """
    Validate connectivity between a cloudify agent and an AMQP server
    :param current_amqp: If set to True, validation is done against the
    current manager's AMQP. If set to False, validation is done against the
    old manager's AMQP to which the agent is currently connected.
    Note: in case of an in-place upgrade, both AMQP servers should be identical
    :param manager_ip: the IP of the current leader (master) Manager, relevant
    only in HA cluster. This IP is used to validate that an agent is connected
    to the Manager's RabbitMQ.
    :param manager_certificate: the SSL certificate of the current leader
    (master) Manager.
    """
    if 'cloudify_agent' not in ctx.instance.runtime_properties:
        raise NonRecoverableError(
            'cloudify_agent key not available in runtime_properties')
    agent = ctx.instance.runtime_properties['cloudify_agent']
    _update_broker_config(agent, manager_ip, manager_certificate)

    validator = _validate_current_amqp if current_amqp else _validate_old_amqp
    result = validator(agent)

    result['timestamp'] = time.time()
    ctx.instance.runtime_properties['agent_status'] = result

    if current_amqp and not result['agent_alive']:
        raise NonRecoverableError(result['agent_alive_error'])
    if not current_amqp and not result['agent_alive_crossbroker']:
        raise NonRecoverableError(result['agent_alive_crossbroker_error'])


def _get_broker_config(agent):
    """
    Return a dictionary with params used to connect to AMQP
    """
    return {
        'broker_ip': agent.get('broker_ip'),
        'broker_port': BROKER_PORT_SSL,
        'broker_ssl_enabled': True
    }


def _update_broker_config(agent, manager_ip, manager_cert):
    if not manager_ip and not manager_cert:
        return
    broker_conf = agent.setdefault('broker_config', dict())
    if manager_ip:
        agent['broker_ip'] = manager_ip
        agent['rest_host'] = manager_ip
        package_url = agent['package_url']
        agent['package_url'] = _create_package_url(package_url, manager_ip)
        broker_conf['broker_ip'] = manager_ip
    if manager_cert:
        broker_conf['broker_ssl_cert'] = manager_cert
    update_agent_runtime_properties(agent)


def _conceal_amqp_password(url):
    """
    replace the broker password in the url before printing it
    """
    before_password = url[:url.find(':', 5)]
    after_password = url[url.find('@'):]
    final = before_password + ':***' + after_password
    return final


def _create_package_url(url, ip):
    before, rest = url.split('//')
    after = rest.split(':')[1]
    new = '{before}//{ip}:{after}'.format(before=before, ip=ip, after=after)
    return new
