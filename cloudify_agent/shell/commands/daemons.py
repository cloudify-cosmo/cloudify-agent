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
import os

from cloudify_agent.api import defaults
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.shell import env
from cloudify_agent.shell.decorators import handle_failures
from cloudify_agent.shell.commands import cfy


class _ExpandUserPath(click.Path):
    """Like click.Path but also calls os.path.expanduser"""
    def convert(self, value, param, ctx):
        value = os.path.expanduser(value)
        return super(_ExpandUserPath, self).convert(value, param, ctx)


@cfy.command(context_settings=dict(ignore_unknown_options=True))
@click.option('--name',
              help='The name of the daemon. [env {0}]'.format(env.AGENT_NAME),
              envvar=env.AGENT_NAME)
@click.option('--user',
              help='The user to create this daemon under. [env {0}]'
                   .format(env.CLOUDIFY_DAEMON_USER),
              envvar=env.CLOUDIFY_DAEMON_USER)
@click.argument('custom-options', nargs=-1, type=click.UNPROCESSED)
@handle_failures
def create(name, user, **params):
    """Creates and stores the daemon parameters"""
    attributes = dict(**params)
    custom_arg = attributes.pop('custom_options', ())
    attributes.update(_parse_custom_options(custom_arg))

    click.echo('Creating...')
    daemon = _load_daemon(name, user=user)
    daemon.create()
    daemon.configure()
    click.echo(f'Successfully created daemon: {daemon.name}')


@cfy.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'.format(env.AGENT_NAME),
              required=True,
              envvar=env.AGENT_NAME)
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


@cfy.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'.format(env.AGENT_NAME),
              required=True,
              envvar=env.AGENT_NAME)
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
    daemon.stop(interval=interval, timeout=timeout)
    click.secho('Successfully stopped daemon: {0}'.format(name))


@cfy.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'.format(env.AGENT_NAME),
              required=True,
              envvar=env.AGENT_NAME)
@handle_failures
def restart(name):

    """
    Restarts the daemon.

    """

    click.echo('Restarting...')
    daemon = _load_daemon(name)
    daemon.restart()
    click.echo('Successfully restarted daemon: {0}'.format(name))


@cfy.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'.format(env.AGENT_NAME),
              required=True,
              envvar=env.AGENT_NAME)
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


@cfy.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'.format(env.AGENT_NAME),
              required=True,
              envvar=env.AGENT_NAME)
@handle_failures
def inspect(name):

    """
    Inspect daemon properties.

    """

    daemon = _load_daemon(name)
    click.echo(json.dumps(daemon.as_dict(), indent=2))


@cfy.command('list')
@handle_failures
def ls():

    """
    List all existing daemons.

    """

    from cloudify_agent.shell.main import get_logger
    daemons = DaemonFactory().load_all(logger=get_logger())
    for daemon in daemons:
        click.echo(daemon.name)


@cfy.command()
@click.option('--name',
              help='The name of the daemon. [env {0}]'.format(env.AGENT_NAME),
              required=True,
              envvar=env.AGENT_NAME)
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
