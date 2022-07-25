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
import re
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

    if disable_requiretty:
        click.echo('Disabling requiretty directive in sudoers file')
        _disable_requiretty(no_sudo)
        click.echo('Successfully disabled requiretty for cfy-agent')
    if relocated_env:
        _relocate_venv()


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


def _relocate_venv():
    """Rewrite the activate script in the virtualenv.

    The only part of the virtualenv that contains hardcoded paths - to the
    build environment - is the activate script. Let's rewrite the path
    in it (which is typically going to be something like /home/jenkins/...),
    with the path of the virtualenv itself.

    This way, the activate script will still work, allowing the user to
    source it and use the agent's python.
    """
    bin_dir = os.path.dirname(sys.executable)
    env_dir = os.path.dirname(bin_dir)
    activate_script = os.path.join(bin_dir, 'activate')
    try:
        with open(activate_script, 'r+') as f:
            content = f.read()
            replaced = re.sub(
                '^VIRTUAL_ENV=.*$',
                'VIRTUAL_ENV="{0}"'.format(env_dir),
                content,
                count=1,
                flags=re.MULTILINE,
            )
            f.seek(0)
            f.truncate()
            f.write(replaced)
    except IOError as e:
        click.echo('Error rewriting venv activate: {0}'.format(e))
