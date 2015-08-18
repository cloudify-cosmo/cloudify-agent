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

from cloudify_agent.shell.decorators import handle_failures
from cloudify_agent.installer.operations import prepare_local_installer


@click.command()
@click.option('--agent-file',
              help='Path to dictionary describing agent to install.',
              type=click.File())
@handle_failures
def install_local(agent_file):
    if agent_file is None:
        raise click.ClickException('--agent-file should be specified.')
    cloudify_agent = json.load(agent_file)
    os.environ['CELERY_BROKER_URL'] = cloudify_agent['broker_url']
    installer = prepare_local_installer(cloudify_agent)
    installer.create_agent()
    installer.configure_agent()
    installer.start_agent()
