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

import click

from cloudify_agent.api import utils as api_utils
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
@handle_failures
def configure(disable_requiretty, relocated_env):

    """
    Configures global agent properties.
    """

    click.echo('Configuring...')
    if disable_requiretty:
        api_utils.disable_requiretty()
    if relocated_env:
        api_utils.fix_virtualenv()
    click.echo('Successfully configured cfy-agent')
