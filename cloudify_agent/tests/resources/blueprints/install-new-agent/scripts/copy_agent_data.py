from cloudify import ctx

for key in ['cloudify_agent', 'agent_status']:
    if key in ctx.target.instance.runtime_properties:
        ctx.source.instance.runtime_properties[key] = \
            ctx.target.instance.runtime_properties[key]
