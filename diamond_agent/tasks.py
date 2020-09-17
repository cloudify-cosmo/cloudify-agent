from cloudify import ctx
from cloudify.decorators import operation


@operation
def install(**_):
    ctx.logger.warn(
        'Diamond plugin functionality is deprecated in Cloudify 5. '
        'Doing nothing.')


@operation
def uninstall(**_):
    ctx.logger.warn(
        'Diamond plugin functionality is deprecated in Cloudify 5. '
        'Doing nothing.')


@operation
def start(**_):
    ctx.logger.warn(
        'Diamond plugin functionality is deprecated in Cloudify 5. '
        'Doing nothing.')


@operation
def stop(**_):
    ctx.logger.warn(
        'Diamond plugin functionality is deprecated in Cloudify 5. '
        'Doing nothing.')


@operation
def add_collectors(**_):
    ctx.logger.warn(
        'Diamond plugin functionality is deprecated in Cloudify 5. '
        'Doing nothing.')


@operation
def del_collectors(**_):
    ctx.logger.warn(
        'Diamond plugin functionality is deprecated in Cloudify 5. '
        'Doing nothing.')
