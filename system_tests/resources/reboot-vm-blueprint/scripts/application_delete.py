from cloudify import ctx


ctx.logger.info('Deleting application')
ctx.instance.runtime_properties['value'] = \
    ctx.node.properties['value']
