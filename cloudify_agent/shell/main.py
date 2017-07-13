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
import logging
import pkgutil

import click

from cloudify.utils import setup_logger

from cloudify_agent.api.utils import logger as api_utils_logger

# adding all of our commands.

from cloudify_agent.shell.commands import daemons
from cloudify_agent.shell.commands import configure
from cloudify_agent.shell.commands import installer


_logger = setup_logger('cloudify_agent.shell.main',
                       logger_format='%(message)s',
                       logger_level=logging.INFO)


def get_logger():
    return _logger


def show_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return

    data = pkgutil.get_data('cloudify_agent', 'VERSION')
    ver = json.loads(data)['version']
    logger = get_logger()
    logger.info('Cloudify Agent {0}'.format(ver))
    ctx.exit()


@click.group()
@click.option('--debug', default=False, is_flag=True)
@click.option('--version', is_flag=True, callback=show_version,
              expose_value=False, is_eager=True, help='Show version and exit')
def main(debug):

    if debug:

        # configure global logger level
        global _logger
        _logger.setLevel(logging.DEBUG)

        # configure api loggers so that there logging level does not rely
        # on imports from the shell modules
        api_utils_logger.setLevel(logging.DEBUG)


@click.group('daemons')
def daemon_sub_command():
    pass


@click.group('plugins')
def plugins_sub_command():
    pass


main.add_command(configure.configure)

daemon_sub_command.add_command(daemons.create)
daemon_sub_command.add_command(daemons.configure)
daemon_sub_command.add_command(daemons.start)
daemon_sub_command.add_command(daemons.stop)
daemon_sub_command.add_command(daemons.delete)
daemon_sub_command.add_command(daemons.restart)
daemon_sub_command.add_command(daemons.inspect)
daemon_sub_command.add_command(daemons.ls)
daemon_sub_command.add_command(daemons.status)

main.add_command(daemon_sub_command)
main.add_command(plugins_sub_command)

main.add_command(installer.install_local)
