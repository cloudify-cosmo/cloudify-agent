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
import sys
import click

from cloudify_agent.api import utils
from cloudify.utils import LocalCommandRunner
from cloudify_agent.shell.decorators import handle_failures
from cloudify_agent.shell.commands import cfy


@cfy.command()
@click.option('--disable-requiretty',
              help='Disables the requiretty directive in the sudoers file.',
              is_flag=True)
@click.option('--fix-shebangs',
              help='Fixes shebangs in scripts.',
              is_flag=True)
@click.option('--no-sudo',
              help='Indication whether sudo should be used when applying '
                   ' disable-requiretty part',
              is_flag=True)
@handle_failures
def configure(disable_requiretty, fix_shebangs, no_sudo):

    """
    Configures global agent properties.
    """

    if disable_requiretty:
        click.echo('Disabling requiretty directive in sudoers file')
        _disable_requiretty(no_sudo)
        click.echo('Successfully disabled requiretty for cfy-agent')
    if fix_shebangs:
        click.echo('Fixing shebangs in scripts')
        _fixup_scripts()


def _fixup_scripts():
    """Make scripts in bin_dir relative by rewriting their shebangs

    Examine each file in bin_dir - if it looks like a python script, and has a
    shebang - replace it with a shebang pointing to the agent's python.
    """
    from cloudify_agent.shell.main import get_logger
    logger = get_logger()

    new_shebang = f"#!{sys.executable}"
    logger.debug('New shebang = %s', new_shebang)
    for filename in _find_scripts_to_fix(os.path.dirname(sys.executable)):
        logger.debug('Rewriting shebangs in script {0}'.format(
            filename))
        _rewrite_shebang(filename, new_shebang)


def _find_scripts_to_fix(bin_dir):
    """Search bin_dir for files that look like python scripts with a shebang
    """
    for filename in os.listdir(bin_dir):
        filename = os.path.join(bin_dir, filename)
        if not os.path.isfile(filename):   # ignore subdirs, e.g. .svn ones
            continue

        try:
            shebang = open(filename, 'rb').readline().decode('utf-8')
        except UnicodeDecodeError:
            # This is probably a binary program, not a script. Just ignore it.
            continue

        if not (shebang.startswith('#!') and 'bin/python' in shebang):
            # the file doesn't have a /../bin/python shebang? nothing to fix
            continue

        yield filename


def _rewrite_shebang(filename, new_shebang):
    """Replace the first line of the file with the new shebang"""
    with open(filename, 'rb') as f:
        lines = f.read().decode('utf-8').splitlines()

    script = [new_shebang] + lines[1:]

    with open(filename, 'wb') as f:
        f.write('\n'.join(script).encode('utf-8'))


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
        resource_path='disable-requiretty.sh',
        executable=True
    )
    runner.run('chmod +x {0}'.format(disable_requiretty_script_path))
    maybe_sudo = '' if no_sudo else 'sudo'
    runner.run('{0} {1}'.format(disable_requiretty_script_path, maybe_sudo))
