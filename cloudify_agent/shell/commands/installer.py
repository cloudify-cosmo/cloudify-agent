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
import json
import click

from cloudify import state, context
from cloudify_agent.api import utils, defaults
from cloudify_agent.installer.config import configuration
from cloudify_agent.shell.decorators import handle_failures
from cloudify_agent.shell.env import CLOUDIFY_LOCAL_REST_CERT_PATH
from cloudify_agent.installer.operations import prepare_local_installer


@click.command('install-local')
@click.option('--agent-file',
              help='Path to dictionary describing agent to install.',
              type=click.File())
@click.option('--output-agent-file',
              help='Path to output agent configuration')
@click.option('--rest-token',
              help='The rest token with which to download the package')
@click.option('--rest-cert-path',
              help='The temporary path to the rest certificate')
@handle_failures
def install_local(agent_file, output_agent_file, rest_token, rest_cert_path):
    if agent_file is None:
        raise click.ClickException('--agent-file should be specified.')
    cloudify_agent = json.load(agent_file)
    ctx = context.CloudifyContext({'rest_token': rest_token})
    state.current_ctx.set(ctx, {})
    if not cloudify_agent.get('rest_port'):
        cloudify_agent['rest_port'] = defaults.INTERNAL_REST_PORT
    os.environ[utils.internal.CLOUDIFY_DAEMON_USER_KEY] = str(
        cloudify_agent['user'])
    os.environ[CLOUDIFY_LOCAL_REST_CERT_PATH] = str(rest_cert_path)
    if 'basedir' not in cloudify_agent:
        cloudify_agent['basedir'] = utils.get_home_dir(cloudify_agent['user'])
    configuration.directory_attributes(cloudify_agent)
    installer = prepare_local_installer(cloudify_agent)
    installer.create_agent()
    installer.configure_agent()
    installer.start_agent()
    if output_agent_file is not None:
        with open(output_agent_file, 'w') as out:
            out.write(json.dumps(cloudify_agent))

    # Remove the temporary cert file, as it was copied to the agent's dir
    os.remove(rest_cert_path)
