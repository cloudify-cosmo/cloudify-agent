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

from cloudify_agent.api.packager.packager import Packager
from cloudify_agent.shell.decorators import handle_failures


@click.command()
@click.option('--config-file',
              help='Packager Config YAML file path')
@click.option('--force',
              help='Overwrites current virtualenv and output package',
              default=False, is_flag=True)
@click.option('--dryrun',
              help='Initiates a Dryrun. Will not create a package',
              default=False, is_flag=True)
@click.option('--no-validate',
              help='Does not validate module installation',
              default=False, is_flag=True)
@click.option('-v', '--verbose', default=False, is_flag=True)
@handle_failures
def create(config_file, force, dryrun, no_validate, verbose):

    """
    Creates a Cloudify Agent Package
    """

    click.echo('Creating agent package...')
    packager = Packager(verbose=verbose)
    packager.create(config=None,
                    config_file=config_file,
                    force=force,
                    dryrun=dryrun,
                    no_validate=no_validate)
    click.echo('Successfully created agent package...')
