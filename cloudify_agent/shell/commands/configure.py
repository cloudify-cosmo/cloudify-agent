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

import os
import click

from cloudify.utils import LocalCommandRunner
from cloudify.exceptions import CommandExecutionException

from cloudify_agent import VIRTUALENV
from cloudify_agent.api import utils
from cloudify_agent.shell.decorators import handle_failures


@click.command()
@click.option('--disable-requiretty',
              help='Disables the requiretty directive in the sudoers file.',
              is_flag=True)
@click.option('--relocated-env',
              help='Indication that this virtualenv was relocated. '
                   'If this option is passed, an auto-correction '
                   'to the virtualenv shabang entries '
                   'will be performed',
              is_flag=True)
@click.option('--no-sudo',
              help='Indication whether sudo should be used when applying '
                   ' disable-requiretty part',
              is_flag=True)
@handle_failures
def configure(disable_requiretty, relocated_env, no_sudo):

    """
    Configures global agent properties.
    """

    click.echo('Configuring...')
    if disable_requiretty:
        click.echo('Disabling requiretty directive in sudoers file')
        _disable_requiretty(no_sudo)
    if relocated_env:
        click.echo('Auto-correcting virtualenv {0}'.format(VIRTUALENV))
        _fix_virtualenv()
    click.echo('Successfully configured cfy-agent')


def _disable_requiretty(no_sudo):

    """
    Disables the requiretty directive in the /etc/sudoers file. This
    will enable operations that require sudo permissions to work properly.

    This is needed because operations are executed
    from within the worker process, which is not a tty process.

    """

    from cloudify_agent.shell.main import get_logger
    runner = LocalCommandRunner(get_logger())

    disable_requiretty_script_path = utils.resource_to_tempfile(
        resource_path='disable-requiretty.sh'
    )
    runner.run('chmod +x {0}'.format(disable_requiretty_script_path))
    maybe_sudo = '' if no_sudo else 'sudo'
    runner.run('{0} {1}'.format(disable_requiretty_script_path, maybe_sudo))


def _fix_virtualenv():

    """
    This method is used for auto-configuration of the virtualenv.
    It is needed in case the environment was created using different paths
    than the one that is used at runtime.

    """

    from cloudify_agent.shell.main import get_logger
    logger = get_logger()

    bin_dir = '{0}/bin'.format(VIRTUALENV)

    logger.debug('Searching for executable files in {0}'.format(bin_dir))
    for executable in os.listdir(bin_dir):
        path = os.path.join(bin_dir, executable)
        logger.debug('Checking {0}...'.format(path))
        if not os.path.isfile(path):
            logger.debug('{0} is not a file. Skipping...'.format(path))
            continue
        if os.path.islink(path):
            logger.debug('{0} is a link. Skipping...'.format(path))
            continue
        basename = os.path.basename(path)
        if basename in ['python', 'python2.7', 'python2.6']:
            logger.debug('{0} is the python executable. Skipping...'
                         .format(path))
            continue
        with open(path) as f:
            lines = f.read().split(os.linesep)
            if lines[0].endswith('/bin/python'):
                new_line = '#!{0}/python'.format(bin_dir)
                logger.debug('Replacing {0} with {1}'
                             .format(lines[0], new_line))
                lines[0] = new_line
        with open(path, 'w') as f:
            f.write(os.linesep.join(lines))

    runner = LocalCommandRunner(logger)

    logger.debug('Searching for links in {0}'.format(VIRTUALENV))
    for link in ['archives', 'bin', 'include', 'lib']:
        link_path = '{0}/local/{1}'.format(VIRTUALENV, link)
        logger.debug('Checking {0}...'.format(link_path))
        try:
            runner.run('unlink {0}'.format(link_path))
            runner.run('ln -s {0}/{1} {2}'
                       .format(VIRTUALENV, link, link_path))
        except CommandExecutionException:
            pass
