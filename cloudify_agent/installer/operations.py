import time

from cloudify.decorators import operation
from cloudify.amqp_client import get_client
from cloudify.models_states import AgentState
from cloudify import ctx, utils as cloudify_utils
from cloudify.exceptions import (
    CommandExecutionError,
    CommandExecutionException,
    NonRecoverableError,
)
from cloudify.agent_utils import (
    create_agent_record,
    update_agent_record,
    get_agent_rabbitmq_user,
    delete_agent_rabbitmq_user,
    delete_agent_queues,
    delete_agent_exchange,
)

from cloudify_agent.api import utils
from cloudify_agent.installer import script

from .config.agent_config import update_agent_runtime_properties
from .config.agent_config import create_agent_config_and_installer


@operation
@create_agent_config_and_installer(new_agent_config=True)
def create(cloudify_agent, installer, **_):
    # When not in "remote" mode, this operation is called only to set the
    # agent_config dict in the runtime properties
    create_agent_record(
        cloudify_agent,
        create_rabbitmq_user=not get_agent_rabbitmq_user(cloudify_agent)
    )
    if cloudify_agent.has_installer:
        with script.install_script_path(cloudify_agent) as script_path:
            ctx.logger.info('Creating Agent {0}'.format(
                cloudify_agent['name']))
            try:
                installer.runner.run_script(script_path)
            except (CommandExecutionError, CommandExecutionException):
                ctx.logger.error("Failed creating agent; marking agent as "
                                 "failed")
                update_agent_record(cloudify_agent, AgentState.FAILED)
                try:
                    ctx.logger.info('Attempting to cleanup after agent %s',
                                    cloudify_agent['name'])
                    installer.stop_agent()
                    installer.delete_agent()
                except Exception as err:
                    ctx.logger.info('Deletion failed: %s', err)
                raise
            ctx.logger.info(
                'Agent created, configured and started successfully'
            )
            update_agent_record(cloudify_agent, AgentState.STARTED)
    elif cloudify_agent.is_proxied:
        ctx.logger.info('Working in "proxied" mode')
    elif cloudify_agent.is_provided:
        ctx.logger.info('Working in "provided" mode')
        _, install_script_download_link = script.install_script_download_link(
            cloudify_agent
        )
        ctx.logger.info(
            'Agent config created. To configure/start the agent, download the '
            'following script: {0}'.format(install_script_download_link)
        )
        cloudify_agent['install_script_download_link'] = \
            install_script_download_link
        update_agent_runtime_properties(cloudify_agent)
        update_agent_record(cloudify_agent, AgentState.CREATED)


@operation
@create_agent_config_and_installer()
def configure(cloudify_agent, installer, **_):
    ctx.logger.info('Configuring Agent {0}'.format(cloudify_agent['name']))
    update_agent_record(cloudify_agent, AgentState.CONFIGURING)
    try:
        installer.configure_agent()
    except CommandExecutionError as e:
        ctx.logger.error(str(e))
        update_agent_record(cloudify_agent, AgentState.FAILED)
        raise
    update_agent_record(cloudify_agent, AgentState.CONFIGURED)


@operation
@create_agent_config_and_installer()
def start(cloudify_agent, **_):
    """
    Only called in "init_script"/"plugin" mode, where the agent is started
    externally (e.g. userdata script), and all we have to do is wait for it
    """
    agent_name = cloudify_agent['queue']
    update_agent_record(cloudify_agent, AgentState.STARTING)
    tenant = cloudify_utils.get_tenant()
    client = get_client(
        amqp_user=tenant['rabbitmq_username'],
        amqp_pass=tenant['rabbitmq_password'],
        amqp_vhost=tenant['rabbitmq_vhost']
    )

    marked_nonresponsive = False
    # we'll wait up to an hour for the agent to start. It really should
    # start sooner than that, but we have to give up eventually.
    start_time = time.time()
    timeout = 3600
    # we can't poll too often, because we need to give the agent a chance to
    # respond. 10 seconds should be PLENTY even on very latency-deficient
    # networks.
    poll_interval = 10
    with client:
        agent_alive = False
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                break
            agent_alive = utils.is_agent_alive(
                name=agent_name,
                client=client,
                timeout=poll_interval,
                connect=False,
            )
            if agent_alive:
                break
            elapsed = time.time() - start_time
            _log = ctx.logger.warning if elapsed > 300 else ctx.logger.info
            _log(
                'Agent %s has not started after %d seconds',
                agent_name, elapsed,
            )
            if elapsed > 300 and not marked_nonresponsive:
                # we've already waited 5 minutes, and the agent still
                # hasn't started. Perhaps the VM is really slow to boot,
                # or there is some problem booting it.
                marked_nonresponsive = True
                update_agent_record(cloudify_agent, AgentState.NONRESPONSIVE)
            time.sleep(poll_interval)

    if not cloudify_agent.is_provided:
        script.cleanup_scripts()

    if agent_alive:
        ctx.logger.info('Agent has started')
        update_agent_record(cloudify_agent, AgentState.STARTED)
    else:
        raise NonRecoverableError(
            f'Agent {agent_name} did not start in {timeout} seconds'
        )


@operation
@create_agent_config_and_installer(validate_connection=False)
def stop(cloudify_agent, installer, **_):
    """
    Only called in "remote" mode - other modes stop via AMQP
    """
    ctx.logger.info('Stopping Agent {0}'.format(cloudify_agent['name']))
    update_agent_record(cloudify_agent, AgentState.STOPPING)
    installer.stop_agent()
    update_agent_record(cloudify_agent, AgentState.STOPPED)
    script.cleanup_scripts()


@operation
@create_agent_config_and_installer(validate_connection=False)
def delete(cloudify_agent, installer, **_):
    update_agent_record(cloudify_agent, AgentState.DELETING)
    # delete the runtime properties set on create
    if cloudify_agent.has_installer:
        ctx.logger.info('Deleting Agent {0}'.format(cloudify_agent['name']))
        installer.delete_agent()
    ctx.instance.runtime_properties.pop('cloudify_agent', None)
    ctx.instance.update()
    update_agent_record(cloudify_agent, AgentState.DELETED)

    delete_agent_rabbitmq_user(cloudify_agent)
    try:
        delete_agent_exchange(cloudify_agent)
        delete_agent_queues(cloudify_agent)
    except KeyError as e:
        # this would happen for malformed cloudify_agent which is missing
        # eg. the tenant data. We'd be possibly leaving queues around,
        # but without that info, we can't really do anything else
        ctx.logger.error('Could not delete agent queues: %s', e)


@operation
@create_agent_config_and_installer()
def restart(cloudify_agent, installer, **_):
    # no need to handling remote_execution False because this operation is
    # not invoked in that case
    ctx.logger.info('Restarting Agent {0}'.format(cloudify_agent['name']))
    update_agent_record(cloudify_agent, AgentState.RESTARTING)
    try:
        installer.restart_agent()
    except CommandExecutionError as e:
        ctx.logger.error(str(e))
        update_agent_record(cloudify_agent, AgentState.FAILED)
        raise
    update_agent_record(cloudify_agent, AgentState.RESTARTED)
