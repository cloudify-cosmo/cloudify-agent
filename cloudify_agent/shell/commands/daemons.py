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

import click
import json

from cloudify_agent.api import defaults
from cloudify_agent.api import utils as api_utils
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.shell import env
from cloudify_agent.shell.decorators import handle_failures


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.option('--process-management',
              help='The process management system to use '
                   'when creating the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_PROCESS_MANAGEMENT),
              type=click.Choice(['init.d', 'nssm', 'detach']),
              required=True,
              envvar=env.CLOUDIFY_DAEMON_PROCESS_MANAGEMENT)
@click.option('--rest-host',
              help='The IP or host name of the REST service [env {0}]'
              .format(env.CLOUDIFY_REST_HOST),
              required=True,
              envvar=env.CLOUDIFY_REST_HOST)
@click.option('--rest-port',
              help='The manager REST port to connect to. [env {0}]'
              .format(env.CLOUDIFY_REST_PORT),
              envvar=env.CLOUDIFY_REST_PORT)
@click.option('--rest-username',
              help='The username to use when sending REST calls. [env {0}]'
              .format(env.CLOUDIFY_REST_USERNAME),
              envvar=env.CLOUDIFY_REST_USERNAME)
@click.option('--rest-password',
              help='The password to use when sending REST calls. [env {0}]'
              .format(env.CLOUDIFY_REST_PASSWORD),
              envvar=env.CLOUDIFY_REST_PASSWORD)
@click.option('--rest-token',
              help='The token to use when sending REST calls. Takes '
                   'precedence over username/password. [env {0}]'
              .format(env.CLOUDIFY_REST_TOKEN),
              envvar=env.CLOUDIFY_REST_TOKEN)
@click.option('--rest-tenant',
              help='The tenant to use when sending REST calls. [env {0}]'
              .format(env.CLOUDIFY_REST_TENANT),
              envvar=env.CLOUDIFY_REST_TENANT)
@click.option('--local-rest-cert-file',
              help='The path to a local copy of the REST public cert, used for'
                   ' cert verification, if required [env {0}]'
              .format(env.CLOUDIFY_LOCAL_REST_CERT_PATH),
              type=click.Path(exists=True, readable=True, file_okay=True),
              envvar=env.CLOUDIFY_LOCAL_REST_CERT_PATH)
@click.option('--name',
              help='The name of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_NAME),
              envvar=env.CLOUDIFY_DAEMON_NAME)
@click.option('--queue',
              help='The name of the queue to register the daemon to. [env {0}]'
                   .format(env.CLOUDIFY_DAEMON_QUEUE),
              envvar=env.CLOUDIFY_DAEMON_QUEUE)
@click.option('--host',
              help='The ip address of the current host. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_HOST),
              envvar=env.CLOUDIFY_DAEMON_HOST)
@click.option('--deployment-id',
              help='The deployment id this daemon will belong to. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_DEPLOYMENT_ID),
              envvar=env.CLOUDIFY_DAEMON_DEPLOYMENT_ID)
@click.option('--user',
              help='The user to create this daemon under. [env {0}]'
                   .format(env.CLOUDIFY_DAEMON_USER),
              envvar=env.CLOUDIFY_DAEMON_USER)
@click.option('--workdir',
              help='Working directory for runtime files (pid, log). '
                   'Defaults to current working directory. [env {0}]'
                   .format(env.CLOUDIFY_DAEMON_WORKDIR),
              envvar=env.CLOUDIFY_DAEMON_WORKDIR)
@click.option('--broker-ip',
              help='The broker host name or ip to connect to. [env {0}]'
                   .format(env.CLOUDIFY_BROKER_IP),
              envvar=env.CLOUDIFY_BROKER_IP)
@click.option('--broker-port',
              help='The broker port to connect to. If not set, this will be '
                   'determined based on whether SSL is enabled. It will be '
                   'set to 5671 with SSL, or 5672 without. [env {0}]'
                   .format(env.CLOUDIFY_BROKER_PORT),
              envvar=env.CLOUDIFY_BROKER_PORT)
@click.option('--broker-user',
              help='The broker username to use. [env {0}]'
                   .format(env.CLOUDIFY_BROKER_USER),
              default='guest',
              envvar=env.CLOUDIFY_BROKER_USER)
@click.option('--broker-pass',
              help='The broker password to use. [env {0}]'
                   .format(env.CLOUDIFY_BROKER_PASS),
              default='guest',
              envvar=env.CLOUDIFY_BROKER_PASS)
@click.option('--broker-ssl-enabled/--broker-ssl-disabled',
              help='Set to "true" to enabled SSL for the broker, or "false" '
                   'to disable SSL for the broker. If this is set, '
                   'broker-ssl-cert-path must also be set. [env {0}]'
                   .format(env.CLOUDIFY_BROKER_SSL_ENABLED),
              default=False,
              envvar=env.CLOUDIFY_BROKER_SSL_ENABLED)
@click.option('--broker-ssl-cert',
              help='The path to the SSL cert for the broker to use.'
                   'Only used when broker-ssl-enable is "true" [env {0}]'
                   .format(env.CLOUDIFY_BROKER_SSL_CERT),
              default=None,
              type=click.Path(exists=True, readable=True, file_okay=True),
              envvar=env.CLOUDIFY_BROKER_SSL_CERT)
@click.option('--broker-ssl-cert-path',
              help='The path to a local copy of the Broker public cert, '
                   'used for cert verification, if required [env {0}]'
              .format(env.CLOUDIFY_BROKER_SSL_CERT_PATH),
              type=click.Path(exists=False, readable=False, file_okay=True),
              envvar=env.CLOUDIFY_BROKER_SSL_CERT_PATH
              )
@click.option('--broker-get-settings-from-manager/'
              '--broker-do-not-get-settings-from-manager',
              default=False,
              help='Whether to retrieve the broker settings from the '
                   'manager. If this is true, broker_user, broker_pass, '
                   'broker_ssl_enabled, and broker_ssl_cert arguments will '
                   'be ignored as these will be obtained from the manager. '
                   '[env {0}]'
                   .format(env.CLOUDIFY_BROKER_GET_SETTINGS_FROM_MANAGER),
              envvar=env.CLOUDIFY_BROKER_GET_SETTINGS_FROM_MANAGER)
@click.option('--min-workers',
              help='Minimum number of workers for '
                   'the autoscale configuration. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_MIN_WORKERS),
              envvar=env.CLOUDIFY_DAEMON_MIN_WORKERS)
@click.option('--max-workers',
              help='Maximum number of workers for '
                   'the autoscale configuration. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_MAX_WORKERS),
              envvar=env.CLOUDIFY_DAEMON_MAX_WORKERS)
@click.option('--log-level',
              help='Log level of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_LOG_LEVEL),
              envvar=env.CLOUDIFY_DAEMON_LOG_LEVEL)
@click.option('--pid-file',
              help='Path to a location where the daemon pid file will be '
                   'stored. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_PID_FILE),
              envvar=env.CLOUDIFY_DAEMON_PID_FILE)
@click.option('--log-file',
              help='Path to a location where the daemon log file will be '
                   'stored. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_LOG_FILE),
              envvar=env.CLOUDIFY_DAEMON_LOG_FILE)
@click.option('--extra-env-path',
              help='Path to an environment file to be added to the daemon. ['
                   'env {0}]'
                   .format(env.CLOUDIFY_DAEMON_EXTRA_ENV),
              envvar=env.CLOUDIFY_DAEMON_EXTRA_ENV)
@click.option('--bypass-maintenance-mode',
              help='bypass maintenance mode on rest requests. [env {0}]'
                   .format(env.CLOUDIFY_BYPASS_MAINTENANCE_MODE),
              envvar=env.CLOUDIFY_BYPASS_MAINTENANCE_MODE)
# this is defined in order to allow passing any kind of option to the
# command line. in order to support creating daemons of different kind via
# the same command line. this argument is parsed as keyword arguments which
# are later passed to the daemon constructor.
@click.argument('custom-options', nargs=-1, type=click.UNPROCESSED)
@handle_failures
def create(**params):

    """
    Creates and stores the daemon parameters.

    """
    attributes = dict(**params)
    custom_arg = attributes.pop('custom_options', ())
    attributes.update(_parse_custom_options(custom_arg))

    click.echo('Creating...')

    if attributes['broker_get_settings_from_manager']:
        broker = api_utils.internal.get_broker_configuration(attributes)
        attributes.update(broker)

    from cloudify_agent.shell.main import get_logger
    daemon = DaemonFactory().new(
        logger=get_logger(),
        **attributes
    )

    daemon.create()
    _save_daemon(daemon)
    click.echo('Successfully created daemon: {0}'
               .format(daemon.name))


@click.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_NAME),
              required=True,
              envvar=env.CLOUDIFY_DAEMON_NAME)
@click.option('--user',
              help='The user to load the configuration from. Defaults to '
                   'current user. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_USER),
              envvar=env.CLOUDIFY_DAEMON_USER)
@handle_failures
def configure(name, user=None):

    """
    Configures the daemon scripts and configuration files.

    """

    click.echo('Configuring...')
    daemon = _load_daemon(name, user=user)
    daemon.configure()
    _save_daemon(daemon)
    click.echo('Successfully configured daemon: {0}'
               .format(daemon.name))


@click.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_NAME),
              required=True,
              envvar=env.CLOUDIFY_DAEMON_NAME)
@click.option('--user',
              help='The user to load the configuration from. Defaults to '
                   'current user. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_USER),
              envvar=env.CLOUDIFY_DAEMON_USER)
@click.option('--interval',
              help='The interval in seconds to sleep when waiting '
                   'for the daemon to be ready.',
              default=defaults.START_INTERVAL)
@click.option('--timeout',
              help='The timeout in seconds to wait '
                   'for the daemon to be ready.',
              default=defaults.START_TIMEOUT)
@click.option('--no-delete-amqp-queue',
              help='Option to prevent deletion of a pre-existing '
                   'queue that this daemon is listening to before the agent.',
              is_flag=True,
              default=not defaults.DELETE_AMQP_QUEUE_BEFORE_START)
@handle_failures
def start(name, interval, timeout, no_delete_amqp_queue, user=None):

    """
    Starts the daemon.

    """

    click.echo('Starting...')
    daemon = _load_daemon(name, user=user)
    daemon.start(
        interval=interval,
        timeout=timeout,
        delete_amqp_queue=not no_delete_amqp_queue
    )
    click.echo('Successfully started daemon: {0}'.format(name))


@click.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_NAME),
              required=True,
              envvar=env.CLOUDIFY_DAEMON_NAME)
@click.option('--interval',
              help='The interval in seconds to sleep when waiting '
                   'for the daemon to stop.',
              default=defaults.STOP_INTERVAL)
@click.option('--timeout',
              help='The timeout in seconds to wait '
                   'for the daemon to stop.',
              default=defaults.STOP_TIMEOUT)
@handle_failures
def stop(name, interval, timeout):

    """
    Stops the daemon.

    """

    click.echo('Stopping...')
    daemon = _load_daemon(name)
    daemon.stop(
        interval=interval,
        timeout=timeout
    )
    click.secho('Successfully stopped daemon: {0}'.format(name))


@click.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_NAME),
              required=True,
              envvar=env.CLOUDIFY_DAEMON_NAME)
@handle_failures
def restart(name):

    """
    Restarts the daemon.

    """

    click.echo('Restarting...')
    daemon = _load_daemon(name)
    daemon.restart()
    click.echo('Successfully restarted daemon: {0}'.format(name))


@click.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_NAME),
              required=True,
              envvar=env.CLOUDIFY_DAEMON_NAME)
@handle_failures
def delete(name):

    """
    Deletes the daemon.

    """

    click.echo('Deleting...')
    daemon = _load_daemon(name)
    daemon.delete()
    DaemonFactory().delete(name)
    click.echo('Successfully deleted daemon: {0}'.format(name))


@click.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_NAME),
              required=True,
              envvar=env.CLOUDIFY_DAEMON_NAME)
@handle_failures
def inspect(name):

    """
    Inspect daemon properties.

    """

    daemon = _load_daemon(name)
    click.echo(json.dumps(api_utils.internal.daemon_to_dict(daemon), indent=2))


@click.command('list')
@handle_failures
def ls():

    """
    List all existing daemons.

    """

    from cloudify_agent.shell.main import get_logger
    daemons = DaemonFactory().load_all(logger=get_logger())
    for daemon in daemons:
        click.echo(daemon.name)


@click.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_NAME),
              required=True,
              envvar=env.CLOUDIFY_DAEMON_NAME)
@handle_failures
def status(name):
    _load_daemon(name).status()


def _load_daemon(name, user=None):
    from cloudify_agent.shell.main import get_logger
    return DaemonFactory(username=user).load(name, logger=get_logger())


def _save_daemon(daemon):
    DaemonFactory(username=daemon.user).save(daemon)


def _parse_custom_options(options):

    parsed = {}
    for option_string in options:
        parts = option_string.split('=')
        key = parts[0][2:].replace('-', '_')  # options start with '--'
        if len(parts) == 1:
            # flag given
            value = True
        else:
            value = parts[1]
        parsed[key] = value

    return parsed
