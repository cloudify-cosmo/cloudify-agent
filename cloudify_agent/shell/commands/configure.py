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

from virtualenv import (OK_ABS_SCRIPTS, is_win, path_locations,
                        fixup_pth_and_egg_link, relative_script)

from cloudify.utils import LocalCommandRunner

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
    # this code is mostly taken from virtualenv; we can't use virtualenv's
    # make_environment_relocatable because it checks if the old shebang
    # points to the virtualenv dir, and packaged agents use a non-existent
    # /tmp path. So, we copied _fixup_scripts mostly intact, but disabled
    # the shebang checking.
    _make_environment_relocatable(VIRTUALENV)


def _make_environment_relocatable(home_dir):
    home_dir, lib_dir, inc_dir, bin_dir = path_locations(home_dir)

    _fixup_scripts(bin_dir)
    fixup_pth_and_egg_link(home_dir)


def _fixup_scripts(bin_dir):
    """Make scripts in bin_dir relative by rewriting their shebangs

    Examine each file in bin_dir - if it looks like a python script, and has a
    shebang - replace it with a new, "relative" shebang. (like
    `virtualenv --relocatable` would)

    The relative shebang is platform-specific, but on linux it will consist
    of a /usr/bin/env shebang, and a python snippet that runs the `activate`
    script.
    """
    from cloudify_agent.shell.main import get_logger
    logger = get_logger()

    new_shebang = _get_relative_shebang()
    for filename in _find_scripts_to_fix(bin_dir):
        logger.debug('Making script {0} relative'.format(filename))
        _rewrite_shebang(filename, new_shebang)


def _find_scripts_to_fix(bin_dir):
    """Search bin_dir for files that look like python scripts with a shebang
    """
    for filename in os.listdir(bin_dir):

        if filename in OK_ABS_SCRIPTS:
            continue

        filename = os.path.join(bin_dir, filename)
        if not os.path.isfile(filename):
            # ignore subdirs, e.g. .svn ones.
            continue

        with open(filename, 'rb') as f:
            try:
                lines = f.read().decode('utf-8').splitlines()
            except UnicodeDecodeError:
                # This is probably a binary program instead
                # of a script, so just ignore it.
                continue

        if not lines:
            continue

        shebang = lines[0]
        if not (shebang.startswith('#!') and 'bin/python' in shebang):
            # the file doesn't have a /../bin/python shebang? nothing to fix
            continue

        yield filename


def _rewrite_shebang(filename, new_shebang):
    """Replace the first line of the file with the new shebang"""
    with open(filename, 'rb') as f:
        lines = f.read().decode('utf-8').splitlines()

    script = relative_script([new_shebang] + lines[1:])

    with open(filename, 'wb') as f:
        f.write('\n'.join(script).encode('utf-8'))


def _get_relative_shebang():
    """Get a shebang that's ok to use in "relative" scripts.

    Platform-specific: on linux, it'll be using /usr/bin/env
    """
    if is_win:
        envpath = '{0} /c'.format(
            os.path.normcase(os.environ.get('COMSPEC', 'cmd.exe')))
        ver = ''
        extension = '.exe'
    else:
        envpath = '/usr/bin/env'
        ver = sys.version[:3]
        extension = ''

    return '#!{0} python{1}{2}'.format(envpath, ver, extension)
