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

from cloudify import ctx

from cloudify_agent.installer import exceptions

#######################################################################
# these are all the attributes exposed by the cloudify_agent property.
# adding an attribute here will automatically make it available via an
# operation input, runtime property, node property or bootstrap context
#######################################################################

AGENT_ATTRIBUTES = {

    'local': {
        'group': 'connection'
    },
    'user': {
        'group': 'connection'
    },
    'uri': {
        'group': 'connection'
    },
    'protocol': {
        'group': 'connection'
    },
    'ip': {
        'group': 'connection'
    },
    'key': {
        'context_attribute': 'agent_key_path',
        'group': 'connection'
    },
    'password': {
        'group': 'connection'
    },
    'port': {
        'context_attribute': 'remote_execution_port',
        'group': 'connection',
    },
    'fabric_env': {
        'group': 'connection',
        'default': {}
    },
    'remote_execution': {
        'group': 'connection',
    },
    'windows': {
        'group': 'connection'
    },
    'ssl_cert_path': {
        'group': 'connection'
    },
    'rest_host': {
        'group': 'cfy-agent'
    },
    'rest_port': {
        'group': 'cfy-agent'
    },
    'rest_token': {
        'group': 'cfy-agent'
    },
    'rest_tenant': {
        'group': 'cfy-agent'
    },
    'agent_rest_cert_path': {
        'group': 'cfy-agent'
    },
    'broker_ssl_cert_path': {
        'group': 'cfy-agent'
    },
    'broker_ssl_cert': {
        'group': 'cfy-agent'
    },
    'queue': {
        'group': 'cfy-agent'
    },
    'name': {
        'group': 'cfy-agent'
    },
    'service_name': {
        'group': 'cfy-agent'
    },
    'process_management': {
        'group': 'cfy-agent'
    },
    'min_workers': {
        'group': 'cfy-agent',
        'default': 0
    },
    'max_workers': {
        'group': 'cfy-agent',
        'default': 5
    },
    'broker_ip': {
        'group': 'cfy-agent'
    },
    'broker_get_settings_from_manager': {
        'group': 'cfy-agent',
        'default': True,
    },
    'disable_requiretty': {
        'group': 'cfy-agent',
        'default': True
    },
    'env': {
        'group': 'cfy-agent',
        'default': {}
    },
    'basedir': {
        'group': 'installation'
    },
    'system_python': {
        'group': 'installation',
        'default': 'python'
    },
    'agent_dir': {
        'group': 'installation'
    },
    'workdir': {
        'group': 'installation'
    },
    'envdir': {
        'group': 'installation'
    },
    'requirements': {
        'group': 'installation'
    },
    'distro': {
        'group': 'installation'
    },
    'distro_codename': {
        'group': 'installation'
    },
    'package_url': {
        'group': 'installation'
    },
    'source_url': {
        'group': 'installation'
    }
}


def raise_missing_attribute(attribute_name):
    raise exceptions.AgentInstallerConfigurationError(
        '{0} must be set in one of the following:\n{1}'
        .format(attribute_name, _create_configuration_options())
    )


def raise_missing_attributes(*attributes):
    raise exceptions.AgentInstallerConfigurationError(
        '{0} must be set in one of the following:\n{1}'
        .format(' or '.join(attributes), _create_configuration_options())
    )


def _create_configuration_options():
    inputs_path = '{0}.interfaces.[{1}].inputs.' \
                  'agent_config' \
        .format(ctx.node.name, ctx.task_name)
    properties_path = '{0}.properties.agent_config'.format(
        ctx.node.name
    )
    runtime_properties_path = \
        '{0}.runtime_properties.cloudify_agent' \
        .format(ctx.instance.id)
    context_path = 'bootstrap_context.cloudify_agent'
    return '1. {0} \n' \
           '2. {1} \n' \
           '3. {2} \n' \
           '4. {3}'.format(inputs_path, runtime_properties_path,
                           properties_path, context_path)
