#########
# Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
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

import click

from cloudify_agent.api import defaults
from cloudify_agent.shell import env
from cloudify_agent.shell.daemon_factory import DaemonFactory
from cloudify_agent.shell.main import handle_failures
from cloudify_agent.shell.main import get_log_level
from cloudify_agent.shell import utils
from cloudify_agent.shell import exceptions


@click.command(context_settings=dict(ignore_unknown_options=True))
@click.option('--manager-ip',
              help='The manager IP to connect to. [env {0}]'
              .format(env.CLOUDIFY_MANAGER_IP),
              required=True,
              envvar=env.CLOUDIFY_MANAGER_IP)
@click.option('--manager-port',
              help='The manager REST gateway port to connect to. [env {0}]'
              .format(env.CLOUDIFY_MANAGER_PORT),
              envvar=env.CLOUDIFY_MANAGER_PORT)
@click.option('--name',
              help='The name of the daemon. [env {0}]'
              .format(env.CLOUDIFY_DAEMON_NAME),
              envvar=env.CLOUDIFY_DAEMON_NAME)
@click.option('--queue',
              help='The name of the queue to register the agent to. [env {0}]'
                   .format(env.CLOUDIFY_DAEMON_QUEUE),
              envvar=env.CLOUDIFY_DAEMON_QUEUE)
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
@click.option('--extra-env-path',
              help='Path to an environment file to be added to the daemon. ['
                   'env {0}]'
                   .format(env.CLOUDIFY_DAEMON_EXTRA_ENV),
              envvar=env.CLOUDIFY_DAEMON_EXTRA_ENV)
@click.option('--start-on-boot',
              help='Configure this daemon to start automatically on boot.',
              is_flag=True,
              default=False)
@click.option('--process-management',
              help='The process management system to use '
                   'when creating the daemon. [env {0}]'
                   .format(env.CLOUDIFY_DAEMON_PROCESS_MANAGEMENT),
              type=click.Choice(['init.d']),
              default='init.d',
              envvar=env.CLOUDIFY_DAEMON_PROCESS_MANAGEMENT)
# this is defined in order to allow passing any kind of option to the
# command line. in order to support creating daemons of different kind via
# the same command line. this argument is parsed as keyword arguments and
# passed on the the daemon constructor.
@click.argument('custom-options', nargs=-1, type=click.UNPROCESSED)
@handle_failures
def create(process_management, **params):

    """
    Creates and stores the daemon parameters.

    """

    attributes = dict(**params)
    custom_arg = attributes.pop('custom_options', ())
    attributes.update(utils.parse_custom_options(custom_arg))
    click.echo('Creating...')
    daemon = DaemonFactory.new(
        process_management=process_management,
        logger_level=get_log_level(),
        **attributes
    )

    daemon.create()
    DaemonFactory.save(daemon)
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

    click.echo('Registering...')
    daemon = _load_daemon(name)
    daemon.register(plugin)
    click.echo('Successfully registered {0} with daemon: {1}'
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
@handle_failures
def start(name, interval, timeout):

    """
    Starts the daemon.

    """

    click.echo('Starting...')
    daemon = _load_daemon(name)
    daemon.start(
        interval=interval,
        timeout=timeout
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
    DaemonFactory.delete(name)
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
    daemon_path = os.path.join(
        utils.get_storage_directory(),
        '{0}.json'.format(name)
    )
    if not os.path.exists(daemon_path):
        raise exceptions.CloudifyAgentNotFoundException(name)
    with open(daemon_path) as f:
        click.echo(f.read())


def _load_daemon(name):
    return DaemonFactory.load(name, logger_level=get_log_level())
