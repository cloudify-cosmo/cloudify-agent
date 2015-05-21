#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
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

from cloudify import ctx

from cloudify_agent.installer import exceptions


AGENT_ATTRIBUTES = {

    'local': {
        'mandatory': True,
        'group': 'connection'
    },
    'windows': {
        'mandatory': True,
        'group': 'connection',
        'default': False
    },
    'user': {
        'mandatory': True,
        'group': 'connection'
    },
    'ip': {
        'mandatory': False,
        'group': 'connection'
    },
    'key': {
        'context_attribute': 'agent_key_path',
        'mandatory': False,
        'group': 'connection'
    },
    'password': {
        'mandatory': False,
        'group': 'connection'
    },
    'port': {
        'context_attribute': 'remote_execution_port',
        'mandatory': False,
        'group': 'connection',
        'default': 22
    },
    'fabric_env': {
        'mandatory': False,
        'group': 'connection'
    },
    'manager_ip': {
        'mandatory': True,
        'group': 'cfy-agent'
    },
    'queue': {
        'mandatory': True,
        'group': 'cfy-agent'
    },
    'name': {
        'mandatory': True,
        'group': 'cfy-agent'
    },
    'process_management': {
        'mandatory': True,
        'group': 'cfy-agent'
    },
    'min_workers': {
        'mandatory': False,
        'group': 'cfy-agent'
    },
    'max_workers': {
        'mandatory': False,
        'group': 'cfy-agent'
    },
    'disable_requiretty': {
        'mandatory': False,
        'group': 'cfy-agent'
    },
    'env': {
        'mandatory': False,
        'group': 'cfy-agent'
    },
    'basedir': {
        'mandatory': True,
        'group': 'installation'
    },
    'agent_dir': {
        'mandatory': True,
        'group': 'installation'
    },
    'workdir': {
        'mandatory': True,
        'group': 'installation'
    },
    'envdir': {
        'mandatory': True,
        'group': 'installation'
    },
    'requirements': {
        'mandatory': False,
        'group': 'installation'
    },
    'distro': {
        'mandatory': False,
        'group': 'installation'
    },
    'distro_codename': {
        'mandatory': False,
        'group': 'installation'
    },
    'package_url': {
        'mandatory': False,
        'group': 'installation'
    },
    'source_url': {
        'mandatory': False,
        'group': 'installation'
    }
}


def raise_missing_attribute(attribute_name):

    inputs_path = '{0}.interfaces.[{1}].inputs.' \
                  'cloudify_agent' \
        .format(ctx.node.name, ctx.task_name)
    properties_path = '{0}.properties.cloudify_agent'.format(
        ctx.node.name
    )
    runtime_properties_path = \
        '{0}.runtime_properties.cloudify_agent' \
        .format(ctx.instance.id)
    context_path = 'bootstrap_context.cloudify_agent'
    raise exceptions.AgentInstallerConfigurationError(
        '{0} was not found in any of '
        'the following: 1. {1}; 2. {2}; 3. {3}; 4. {4}'
        .format(attribute_name,
                inputs_path,
                runtime_properties_path,
                properties_path,
                context_path)
    )
