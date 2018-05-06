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
from cloudify import ctx
from cloudify.broker_config import broker_hostname
from cloudify.exceptions import NonRecoverableError, RecoverableError
from cloudify.utils import (ManagerVersion,
                            get_local_rest_certificate)
from cloudify.decorators import operation

from cloudify_agent.celery_app import get_celery_app
from cloudify_agent.api.plugins.installer import PluginInstaller
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.api import exceptions
from cloudify_agent.api import utils
from cloudify_agent.installer.script import \
    init_script_download_link, cleanup_scripts
from cloudify_agent.installer.config.agent_config import CloudifyAgentConfig

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
    ctx.instance.runtime_properties['cloudify_agent'] = cloudify_agent

    # must update instance here because the process may shutdown before
    # the decorator has a chance to do it.
    ctx.instance.update()

    daemon = _load_daemon(logger=ctx.logger)

    # make the current master stop listening to the current queue
    # to avoid a situation where we have two masters listening on the
    # same queue.
    app = get_celery_app(tenant=cloudify_agent['rest_tenant'])
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


def _set_default_new_agent_config_values(
        old_agent, new_agent, transfer_agent=False):
    if not transfer_agent:
        new_agent['name'] = utils.internal.generate_new_agent_name(
            old_agent['name'])
    # Set the broker IP explicitly to the current manager's IP
    new_agent['broker_ip'] = broker_hostname
    new_agent['old_agent_version'] = old_agent['version']
    new_agent['disable_requiretty'] = False
    new_agent['install_with_sudo'] = True
    new_agent['networks'] = ctx.bootstrap_context.cloudify_agent.networks
    new_agent['cluster'] = ctx.bootstrap_context.cloudify_agent.cluster or []


def _copy_values_from_old_agent_config(
        old_agent, new_agent, transfer_agent=False):
    fields_to_copy = ['windows', 'ip', 'basedir', 'user', 'distro_codename',
                      'distro', 'broker_ssl_cert_path', 'agent_rest_cert_path',
                      'network', 'local', 'install_method',
                      'process_management']
    if transfer_agent:
        fields_to_copy.append('name')
    for field in fields_to_copy:
        if field in old_agent:
            new_agent[field] = old_agent[field]


def create_new_agent_config(old_agent, manager_ip=None, transfer_agent=False):
    new_agent = CloudifyAgentConfig()
    _set_default_new_agent_config_values(old_agent, new_agent, transfer_agent)
    _copy_values_from_old_agent_config(old_agent, new_agent, transfer_agent)
    new_agent.set_default_values()
    new_agent.set_installation_params(runner=None)
    new_agent['broker_ip'] = manager_ip
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


def _assert_agent_alive(name, celery_client, version=None):
    tasks = utils.get_agent_registered(name, celery_client)
    # Using RecoverableError to allow retries
    if not tasks:
        raise RecoverableError(
            'Could not access tasks list for agent {0}'.format(name))
    task_name = _celery_task_name(version)
    if task_name not in tasks:
        raise RecoverableError('Task {0} is not available in agent {1}'.
                               format(task_name, name))


def _get_manager_version():
    version_json = cloudify.manager.get_rest_client().manager.get_version()
    return ManagerVersion(version_json['version'])


def _http_rest_host(cloudify_agent):
    return 'http://{0}/'.format(cloudify_agent['rest_host'])


def _get_init_script_path_and_url(new_agent, old_agent_version,
                                  manager_ip=None, manager_cert=None,
                                  rest_token=None, transfer_agent=False):
    script_path, script_url = init_script_download_link(
        new_agent, manager_ip, manager_cert, rest_token, transfer_agent)
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
    return created_agent


def _build_install_script_params(old_agent, script_url):
    script_runner_task = 'script_runner.tasks.run'
    cloudify_context = {
        'type': 'operation',
        'task_name': script_runner_task,
        'task_target': old_agent['queue']
    }
    kwargs = {'script_path': script_url,
              'ssl_cert_content': _get_ssl_cert_content(old_agent['version']),
              '__cloudify_context': cloudify_context}
    return kwargs


def _execute_install_script_task(app, params, old_agent, timeout, script_path):
    task = _celery_task_name(old_agent['version'])
    try:
        result = app.send_task(
            task,
            kwargs=params,
            queue=old_agent['queue']
        )
        result.get(timeout=timeout)
    finally:
        os.remove(script_path)


def _run_install_script(old_agent, timeout, manager_ip=None, manager_cert=None,
                        rest_token=None, transfer_agent=False):
    old_agent = copy.deepcopy(old_agent)
    if 'version' not in old_agent:
        # Assuming that if there is no version info in the agent then
        # this agent was installed by current manager.
        old_agent['version'] = str(_get_manager_version())
    new_agent = create_new_agent_config(old_agent, manager_ip, transfer_agent)
    with _celery_app(old_agent) as celery_app:
        _assert_agent_alive(old_agent['name'], celery_app,
                            old_agent['version'])

        script_path, script_url = _get_init_script_path_and_url(
            new_agent, old_agent['version'], manager_ip, manager_cert,
            rest_token, transfer_agent=transfer_agent
        )
        params = _build_install_script_params(old_agent, script_url)
        _execute_install_script_task(
            celery_app, params, old_agent, timeout, script_path
        )
    cleanup_scripts()
    created_agent = _validate_created_agent(new_agent)
    return {'old': old_agent, 'new': created_agent}


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
             'validation needs to be performed before new agent installation'))
    status = ctx.instance.runtime_properties['agent_status']
    if not status['agent_alive_crossbroker']:
        raise NonRecoverableError(
            ('Last validation attempt has shown that agent is dead. '
             'Rerun validation.'))
    return agent


@operation
def create_agent_amqp(install_agent_timeout=300, manager_ip=None,
                      manager_certificate=None, **_):
    """
    Installs a new agent on a host machine.
    :param install_agent_timeout: operation's timeout.
    :param manager_ip: the private IP of the current leader (master) Manager.
     This IP is used to connect to the Manager's RabbitMQ.
     (relevant only in HA cluser)
    :param manager_certificate: the SSL certificate of the current leader
    (master) Manager. (relevant only in HA cluser)
    """
    old_agent = _validate_agent()
    _update_broker_config(old_agent, manager_ip, manager_certificate)
    agents = _run_install_script(old_agent, install_agent_timeout)
    returned_agent = agents['new']
    ctx.logger.info('Installed agent {0}'.format(returned_agent['name']))

    # Make sure that new celery agent was started:
    app = get_celery_app(tenant=returned_agent['rest_tenant'])
    _assert_agent_alive(returned_agent['name'], app)

    # Setting old_cloudify_agent in order to uninstall it later.
    ctx.instance.runtime_properties['old_cloudify_agent'] = agents['old']
    ctx.instance.runtime_properties['cloudify_agent'] = returned_agent


def _validate_amqp_connection(celery_app, agent_name, agent_version=None):
    broker_url = _conceal_amqp_password(celery_app.conf['BROKER_URL'])
    ctx.logger.info('Checking if agent can be accessed through: {0}'.format(
        broker_url))
    _assert_agent_alive(agent_name, celery_app, agent_version)


def _validate_old_amqp():
    agent = ctx.instance.runtime_properties['cloudify_agent']
    try:
        ctx.logger.info('Trying old AMQP...')
        with _celery_app(agent) as app:
            _validate_amqp_connection(app, agent['name'], agent.get('version'))
    except Exception as e:
        ctx.logger.info('Agent unavailable, reason {0}'.format(str(e)))
        return {
            'agent_alive_crossbroker': False,
            'agent_alive_crossbroker_error': str(e)
        }
    else:
        return {
            'agent_alive_crossbroker': True,
            'agent_alive_crossbroker_error': ''
        }


def _validate_current_amqp():
    agent = ctx.instance.runtime_properties['cloudify_agent']
    _create_broker_config()
    try:
        ctx.logger.info('Trying current AMQP...')
        app = get_celery_app(tenant=agent.get('rest_tenant'))
        _validate_amqp_connection(app, agent['name'])
    # Using RecoverableError to allow retries
    except RecoverableError:
        raise
    except Exception as e:
        ctx.logger.info('Agent unavailable, reason {0}'.format(str(e)))
        return {
            'agent_alive': False,
            'agent_alive_error': str(e)
        }
    else:
        return {
            'agent_alive': True,
            'agent_alive_error': ''
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
    only in HA cluser. This IP is used to validate that an agent is connected
    to the Manager's RabbitMQ.
    :param manager_certificate: the SSL certificate of the current leader
    (master) Manager.
    """
    if 'cloudify_agent' not in ctx.instance.runtime_properties:
        raise NonRecoverableError(
            'cloudify_agent key not available in runtime_properties')
    agent = ctx.instance.runtime_properties['cloudify_agent']
    _update_broker_config(agent, manager_ip, manager_certificate)
    result = _validate_current_amqp() if current_amqp else _validate_old_amqp()

    result['timestamp'] = time.time()
    ctx.instance.runtime_properties['agent_status'] = result

    if current_amqp and not result['agent_alive']:
        raise NonRecoverableError(result['agent_alive_error'])
    if not current_amqp and not result['agent_alive_crossbroker']:
        raise NonRecoverableError(result['agent_alive_crossbroker_error'])


@operation
def transfer_agent_amqp(transfer_agent_timeout=300,
                        manager_ip=None, manager_certificate=None,
                        manager_rest_token=None, **_):

    _create_broker_config(transfer_mode=True)
    old_agent = _validate_agent()
    agents = _run_install_script(old_agent, transfer_agent_timeout, manager_ip,
                                 manager_certificate, manager_rest_token,
                                 transfer_agent=True)
    returned_agent = agents['new']
    ctx.logger.info('Configured agent {0} to work with the new Manager'.
                    format(returned_agent['name']))

    # Make sure the agent is alive:
    app = get_celery_app(tenant=returned_agent['rest_tenant'])
    _assert_agent_alive(returned_agent['name'], app)


def _create_broker_config(transfer_mode=False):
    """
    This function creates a dictionary called 'broker_config' within the
    'cloudify_agent' dict, that contains all the required information that will
     later be used to create a Celery client
    :return:
    """
    if 'cloudify_agent' not in ctx.instance.runtime_properties:
        raise NonRecoverableError(
            'cloudify_agent key not available in runtime_properties')
    agent = ctx.instance.runtime_properties['cloudify_agent']
    if 'broker_config' not in agent:
        agent['broker_config'] = dict()
    broker_conf = agent['broker_config']
    broker_conf['broker_ip'] = agent.get('broker_ip')
    tenant = agent.get('rest_tenant', {})
    broker_conf['broker_user'] = tenant.get('rabbitmq_username')
    broker_conf['broker_vhost'] = tenant.get('rabbitmq_vhost')
    broker_conf['broker_pass'] = tenant.get('rabbitmq_password')
    broker_conf['broker_ssl_enabled'] = True
    if transfer_mode:
        status = ctx.instance.runtime_properties['agent_status']
        status['agent_alive_crossbroker'] = True
        ssl_path = agent.get('broker_ssl_cert_path')
        with open(ssl_path, 'r') as ssl_file:
            ssl_cert = ssl_file.read()
        broker_conf['broker_ssl_cert'] = ssl_cert
    ctx.instance.runtime_properties['cloudify_agent'] = agent
    ctx.instance.update()


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
    ctx.instance.runtime_properties['cloudify_agent'] = agent
    ctx.instance.update()


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
