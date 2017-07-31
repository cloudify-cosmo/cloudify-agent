from cloudify import ctx

from cloudify_agent.installer import exceptions


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
