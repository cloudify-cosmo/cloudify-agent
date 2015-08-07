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

import json
import click

from cloudify_agent.api import defaults
from cloudify_agent.api import utils as api_utils
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.shell import env
from cloudify_agent.shell.decorators import handle_failures


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.option('--manager-ip',
              help='The manager IP to connect to. [env {0}]'
              .format(env.CLOUDIFY_MANAGER_IP),
              required=True,
              envvar=env.CLOUDIFY_MANAGER_IP)
@click.option('--process-management',
              help='The process management system to use '
                   'when creating the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_PROCESS_MANAGEMENT),
              type=click.Choice(['init.d', 'nssm', 'detach']),
              required=True,
              envvar=env.CLOUDIFY_DAEMON_PROCESS_MANAGEMENT)
@click.option('--manager-port',
              help='The manager REST gateway port to connect to. [env {0}]'
              .format(env.CLOUDIFY_MANAGER_PORT),
              envvar=env.CLOUDIFY_MANAGER_PORT)
@click.option('--includes',
              help='A comma separated list of module names '
                   'to be included in the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_INCLUDES),
              envvar=env.CLOUDIFY_DAEMON_INCLUDES)
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
              help='The broker ip to connect to. '
                   'If not specified, the --manager_ip '
                   'option will be used. [{0}]'
                   .format(env.CLOUDIFY_BROKER_IP),
              envvar=env.CLOUDIFY_BROKER_IP)
@click.option('--broker-port',
              help='The broker port to connect to. [env {0}]'
                   .format(env.CLOUDIFY_BROKER_PORT),
              envvar=env.CLOUDIFY_BROKER_PORT)
@click.option('--broker-url',
              help='The broker url to connect to. If this '
                   'option is specified, the broker-ip and '
                   'broker-port options are ignored. [env {0}]'
              .format(env.CLOUDIFY_BROKER_URL),
              envvar=env.CLOUDIFY_BROKER_URL)
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
@handle_failures
def configure(name):

    """
    Configures the daemon scripts and configuration files.

    """

    click.echo('Configuring...')
    daemon = _load_daemon(name)
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
@click.option('--plugin',
              help='The plugin name. As stated in its setup.py file.',
              required=True)
@handle_failures
def register(name, plugin):

    """
    Registers an additional plugin. All methods decorated with the 'operation'
    decorator inside plugin modules will be imported.

    """

    click.echo('Registering plugin {0} in daemon {1}'.format(plugin, name))
    daemon = _load_daemon(name)
    daemon.register(plugin)

    # we need to save the daemon here because the includes attribute
    # has changed - added a new plugin
    _save_daemon(daemon)

    click.echo('Successfully registered {0} with daemon: {1}'
               .format(plugin, name))


@click.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_NAME),
              required=True,
              envvar=env.CLOUDIFY_DAEMON_NAME)
@click.option('--plugin',
              help='The plugin name. As stated in its setup.py file.',
              required=True)
@handle_failures
def unregister(name, plugin):

    """
    Registers an additional plugin. All methods decorated with the 'operation'
    decorator inside plugin modules will be imported.

    """

    click.echo('Un-registering plugin {0} from daemon {1}'
               .format(plugin, name))
    daemon = _load_daemon(name)
    daemon.unregister(plugin)

    # we need to save the daemon here because the includes attribute
    # has changed - removed plugin
    _save_daemon(daemon)

    click.echo('Successfully un-registered {0} from daemon: {1}'
               .format(plugin, name))


@click.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_NAME),
              required=True,
              envvar=env.CLOUDIFY_DAEMON_NAME)
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
def start(name, interval, timeout, no_delete_amqp_queue):

    """
    Starts the daemon.

    """

    click.echo('Starting...')
    daemon = _load_daemon(name)
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


def _load_daemon(name):
    from cloudify_agent.shell.main import get_logger
    return DaemonFactory().load(name, logger=get_logger())


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
