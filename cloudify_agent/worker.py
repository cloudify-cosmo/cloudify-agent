########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
############

import os
import sys
import yaml
import time
import logging
import argparse
import traceback
import threading
from contextlib import contextmanager
from distutils.version import StrictVersion

from cloudify_agent.api import utils
from cloudify_agent.api.factory import DaemonFactory

from cloudify_rest_client.executions import Execution
from cloudify_rest_client.exceptions import (
    CloudifyClientError,
    InvalidExecutionUpdateStatus,
    ExpiredCloudifyLicense,
    MissingCloudifyLicense

)

from cloudify import dispatch, exceptions
from cloudify.logs import setup_agent_logger
from cloudify.utils import get_admin_api_token
from cloudify.models_states import ExecutionState
from cloudify.error_handling import serialize_known_exception
from cloudify.state import current_workflow_ctx, workflow_ctx
from cloudify.constants import MGMTWORKER_QUEUE, EVENTS_EXCHANGE_NAME
from cloudify.manager import update_execution_status, get_rest_client

from cloudify.utils import (get_func,
                            get_admin_api_token,
                            get_rest_token_by_user_id)
from cloudify.amqp_client import (AMQPConnection,
                                  TaskConsumer,
                                  SendHandler,
                                  get_client)


DEFAULT_MAX_WORKERS = 10

SUPPORTED_EXCEPTIONS = (
    exceptions.OperationRetry,
    exceptions.RecoverableError,
    exceptions.NonRecoverableError,
    exceptions.ProcessExecutionError,
    exceptions.HttpException
)

logger = None


def _setup_logger(name):
    global logger
    name = name or 'mgmtworker'
    setup_agent_logger(name)
    logger = logging.getLogger('worker.{0}'.format(name))


class CloudifyOperationConsumer(TaskConsumer):
    routing_key = 'operation'
    handler = dispatch.OperationHandler

    def __init__(self, *args, **kwargs):
        self._registry = kwargs.pop('registry')
        super(CloudifyOperationConsumer, self).__init__(*args, **kwargs)

    def _print_task(self, ctx, action, status=None):
        if ctx['type'] in ['workflow', 'hook']:
            prefix = '{0} {1}'.format(action, ctx['type'])
            suffix = ''
        else:
            prefix = '{0} operation'.format(action)
            suffix = '\n\tNode ID: {0}'.format(ctx.get('node_id'))

        if status:
            suffix += '\n\tStatus: {0}'.format(status)

        tenant_name = ctx.get('tenant', {}).get('name')
        logger.info(
            '\n\t{prefix} on queue `{queue}` on tenant `{tenant}`:\n'
            '\tTask name: {name}\n'
            '\tExecution ID: {execution_id}\n'
            '\tWorkflow ID: {workflow_id}{suffix}\n'.format(
                tenant=tenant_name,
                prefix=prefix,
                name=ctx['task_name'],
                queue=ctx.get('task_target'),
                execution_id=ctx.get('execution_id'),
                workflow_id=ctx.get('workflow_id'),
                suffix=suffix
            )
        )

    def handle_task(self, full_task):
        execution_creator_id = full_task.get('execution_creator')
        task = full_task['cloudify_task']
        ctx = task['kwargs'].pop('__cloudify_context')

        if self.is_scheduled_execution(full_task):
            self.handle_scheduled_execution(ctx, execution_creator_id)

            if not self.can_scheduled_execution_start(ctx['execution_id'],
                                                      ctx['tenant']['name']):
                # Execution can't currently start running, it has been queued.
                return

        self._print_task(ctx, 'Started handling')
        handler = self.handler(cloudify_context=ctx, args=task.get('args', []),
                               kwargs=task['kwargs'],
                               process_registry=self._registry)
        try:
            rv = handler.handle_or_dispatch_to_subprocess_if_remote()
            result = {'ok': True, 'result': rv}
            status = 'SUCCESS - result: {0}'.format(result)
        except SUPPORTED_EXCEPTIONS as e:
            error = serialize_known_exception(e)
            result = {'ok': False, 'error': error}
            status = 'ERROR - result: {0}'.format(result)
            logger.error(
                'ERROR - caught: {0}\n{1}'.format(
                    repr(e), error['traceback']
                )
            )
        self._print_task(ctx, 'Finished handling', status)
        return result

    @staticmethod
    def is_scheduled_execution(full_task):
        """
        If a task contains a `dead-letter-exchange` (dlx_id) information it
        means it was scheduled
        """
        return True if full_task.get('dlx_id') else False

    def handle_scheduled_execution(self, ctx, execution_creator_id):
        # This is a scheduled task. It was sent to mgmtworker queue from a
        # temp queue using a dead-letter-exchange (dlx), need to delete them
        execution_id = ctx['execution_id']
        self.delete_queue(execution_id + '_queue')
        self.delete_exchange(execution_id)

        # Get new valid REST token (of the user who created the execution)
        self.generate_valid_rest_token_and_put_in_ctx(ctx,
                                                      execution_creator_id)

    @staticmethod
    def generate_valid_rest_token_and_put_in_ctx(ctx, execution_creator_id):
        """
        Create a rest client using the admin api token, use this rest client
        to generate a valid REST token of the execution creator and put it
        in the ctx.
        :param execution_creator_id: the user id of the execution creator
        """
        admin_api_token = get_admin_api_token()
        rest_client = get_rest_client(tenant='default_tenant',
                                      api_token=admin_api_token)
        user_rest_token = get_rest_token_by_user_id(rest_client,
                                                    execution_creator_id)
        ctx['rest_token'] = user_rest_token

    @staticmethod
    def can_scheduled_execution_start(execution_id, tenant):
        """
        This method checks whether or not a scheduled execution can currently
        start running. If it can't - it changes the executions status to
        QUEUED (so that it will automatically start running when possible)
        """

        api_token = get_admin_api_token()
        tenant_client = get_rest_client(tenant=tenant, api_token=api_token)
        if tenant_client.executions.should_start(execution_id):
            return True

        tenant_client.executions.update(execution_id, ExecutionState.QUEUED)
        return False


class CloudifyWorkflowConsumer(CloudifyOperationConsumer):
    routing_key = 'workflow'
    handler = dispatch.WorkflowHandler


class ServiceTaskConsumer(TaskConsumer):
    routing_key = 'service'

    def __init__(self, name, *args, **kwargs):
        self.name = name
        self._operation_registry = kwargs.pop('operation_registry')
        self._workflow_registry = kwargs.pop('workflow_registry')
        super(ServiceTaskConsumer, self).__init__(*args, **kwargs)

    def handle_task(self, full_task):
        service_tasks = {
            'ping': self.ping_task,
            'cluster-update': self.cluster_update_task,
            'cancel-workflow': self.cancel_workflow_task,
            'cancel-operation': self.cancel_operation_task
        }

        task = full_task['service_task']
        task_name = task['task_name']
        kwargs = task['kwargs']

        logger.info(
            'Received `{0}` service task with kwargs: {1}'.format(
                task_name, kwargs
            )
        )
        result = service_tasks[task_name](**kwargs)
        logger.info('Result: {0}'.format(result))
        return result

    def ping_task(self):
        return {'time': time.time()}

    def cluster_update_task(self, nodes):
        if not self.name:
            raise RuntimeError('cluster-update sent to agent with no name set')
        factory = DaemonFactory()
        daemon = factory.load(self.name)
        network_name = daemon.network
        nodes = [n['networks'][network_name] for n in nodes]
        daemon.cluster = nodes
        factory.save(daemon)

    def cancel_operation_task(self, execution_id):
        logger.info('Cancelling task {0}'.format(execution_id))
        self._operation_registry.cancel(execution_id)

    def cancel_workflow_task(self, execution_id, rest_token, tenant):
        logger.info('Cancelling workflow {0}'.format(execution_id))

        class CancelCloudifyContext(object):
            """A CloudifyContext that has just enough data to cancel workflows
            """
            def __init__(self):
                self.tenant = tenant
                self.tenant_name = tenant['name']
                self.rest_token = rest_token

        with current_workflow_ctx.push(CancelCloudifyContext()):
            self._workflow_registry.cancel(execution_id)
            self._cancel_agent_operations(execution_id)
            try:
                update_execution_status(execution_id, Execution.CANCELLED)
            except InvalidExecutionUpdateStatus:
                # the workflow process might have cleaned up, and marked the
                # workflow failed or cancelled already
                logger.info('Failed to update execution status: {0}'
                            .format(execution_id))

    def _cancel_agent_operations(self, execution_id):
        """Send a cancel-operation task to all agents for this deployment"""
        rest_client = get_rest_client()
        for target in self._get_agents(rest_client, execution_id):
            self._send_cancel_task(target, execution_id)

    def _send_cancel_task(self, target, execution_id):
        """Send a cancel-operation task to the agent given by `target`"""
        message = {
            'service_task': {
                'task_name': 'cancel-operation',
                'kwargs': {'execution_id': execution_id}
            }
        }
        if target == MGMTWORKER_QUEUE:
            client = get_client()
        else:
            tenant = workflow_ctx.tenant
            client = get_client(
                amqp_user=tenant['rabbitmq_username'],
                amqp_pass=tenant['rabbitmq_password'],
                amqp_vhost=tenant['rabbitmq_vhost']
            )

        handler = SendHandler(exchange=target, routing_key='service')
        client.add_handler(handler)
        with client:
            handler.publish(message)

    def _get_agents(self, rest_client, execution_id):
        """Get exchange names for agents related to this execution.

        Note that mgmtworker is related to all executions, since every
        execution might have a central_deployment_agent operation.
        """
        yield MGMTWORKER_QUEUE
        execution = rest_client.executions.get(execution_id)
        node_instances = rest_client.node_instances.list(
            deployment_id=execution.deployment_id,
            _get_all_results=True)
        for instance in node_instances:
            if self._is_agent(instance):
                yield instance.runtime_properties['cloudify_agent']['queue']

    def _is_agent(self, node_instance):
        """Does the node_instance have an agent?"""
        # Compute nodes are hosts, so checking if host_id is the same as id
        # is a way to check if the node instance is a Compute without
        # querying for the actual Node
        is_compute = node_instance.id == node_instance.host_id
        return (is_compute and
                'cloudify_agent' in node_instance.runtime_properties)


class HookHandler(dispatch.OperationHandler):
    @contextmanager
    def _update_operation_state(self):
        yield


class HookConsumer(CloudifyOperationConsumer):
    routing_key = 'events.hooks'
    HOOKS_CONFIG_PATH = '/opt/mgmtworker/config/hooks.conf'
    handler = HookHandler

    def __init__(self, queue_name, registry, max_workers=5):
        super(HookConsumer, self).__init__(queue_name,
                                           exchange_type='topic',
                                           registry=registry,
                                           threadpool_size=max_workers)
        self.queue = queue_name
        self.exchange = EVENTS_EXCHANGE_NAME

    def handle_task(self, full_task):
        event_type = full_task['event_type']
        hook = self._get_hook(event_type)
        if not hook:
            return
        logger.info(
            'The hook consumer received `{0}` event and the hook '
            'implementation is: `{1}`'.format(event_type,
                                              hook.get('implementation'))
        )

        try:
            task = self._get_task(full_task, hook)
            result = super(HookConsumer, self).handle_task(task)
        except Exception as e:
            result = {'ok': False, 'error': e.message}
            logger.error('{0!r}, while running the hook triggered by the '
                         'event: {1}'.format(e, event_type))
        return result

    def _get_hook(self, event_type):
        if not os.path.exists(self.HOOKS_CONFIG_PATH):
            logger.warn("The hook consumer received `{0}` event but the "
                        "hooks config file doesn't exist".format(event_type))
            return None

        with open(self.HOOKS_CONFIG_PATH) as hooks_conf_file:
            try:
                hooks_yaml = yaml.safe_load(hooks_conf_file)
                hooks_conf = hooks_yaml.get('hooks', {}) if hooks_yaml else {}
            except yaml.YAMLError:
                logger.error(
                    "The hook consumer received `{0}` event but the hook "
                    "config file is invalid yaml".format(event_type)
                )
                return None

        for hook in hooks_conf:
            if hook.get('event_type') == event_type:
                return hook
        logger.info("The hook consumer received `{0}` event but didn't find a "
                    "compatible hook in the configuration".format(event_type))
        return None

    def _get_task(self, full_task, hook):
        hook_context, operation_context = self._get_contexts(
            full_task,
            hook['implementation']
        )
        task = {
            'cloudify_task': {
                'kwargs': {
                    '__cloudify_context': operation_context
                },
                'args': [hook_context]
            }
        }
        kwargs = hook.get('inputs') or {}
        task['cloudify_task']['kwargs'].update(kwargs)
        return task

    def _get_contexts(self, full_task, implementation):
        hook_context = full_task['context']
        tenant = hook_context.pop('tenant')
        tenant_name = tenant.get('name')
        hook_context['tenant_name'] = tenant.get('name')
        hook_context['event_type'] = full_task['event_type']
        hook_context['timestamp'] = full_task['timestamp']
        hook_context['arguments'] = full_task['message']['arguments']
        operation_context = dict(
            type='hook',
            tenant=tenant,
            no_ctx_kwarg=True,
            task_target=self.queue,
            tenant_name=tenant_name,
            plugin=self._get_plugin(tenant_name, implementation)
        )

        if operation_context['plugin']:
            split_task_name = implementation.split('.')[1:]
            operation_context['task_name'] = '.'.join(split_task_name)
        else:
            operation_context['task_name'] = implementation
        return hook_context, operation_context

    def _get_plugin(self, tenant_name, implementation):
        package_name = implementation.split('.')[0]
        filter_plugin = {'package_name': package_name}
        admin_api_token = get_admin_api_token()
        rest_client = get_rest_client(tenant=tenant_name,
                                      api_token=admin_api_token)
        plugins = rest_client.plugins.list(**filter_plugin)
        if not plugins:
            return {}

        plugins.sort(key=lambda p: StrictVersion(p.package_version),
                     reverse=True)
        return {
            'package_name': package_name,
            'package_version': plugins[0]['package_version'],
            'visibility': plugins[0]['visibility']
        }


def _setup_excepthook(daemon_name):
    # Setting a new exception hook to catch any exceptions
    # on agent startup and write them to a file. This file
    # is later read for querying if celery has started successfully.
    current_excepthook = sys.excepthook

    def new_excepthook(exception_type, value, the_traceback):
        # use the storage directory because the work directory might have
        # been created under a different user, in which case we don't have
        # permissions to write to it.
        storage = utils.internal.get_daemon_storage_dir()
        if not os.path.exists(storage):
            os.makedirs(storage)
        error_dump_path = os.path.join(
            utils.internal.get_daemon_storage_dir(),
            '{0}.err'.format(daemon_name))
        with open(error_dump_path, 'w') as f:
            f.write('Type: {0}\n'.format(exception_type))
            f.write('Value: {0}\n'.format(value))
            traceback.print_tb(the_traceback, file=f)
        current_excepthook(exception_type, value, the_traceback)

    sys.excepthook = new_excepthook


class ProcessRegistry(object):
    """A registry for dispatch subprocesses.

    The dispatch TaskHandler uses this to register the subprocesses that
    are running and executing a task, so that they can be cancelled/killed
    from outside.
    """
    def __init__(self):
        self._processes = {}

    def register(self, handler, process):
        self._processes.setdefault(self.make_key(handler), []).append(process)

    def unregister(self, handler, process):
        try:
            self._processes[self.make_key(handler)].remove(process)
        except (KeyError, ValueError):
            pass

    def cancel(self, task_id):
        for p in self._processes.get(task_id, []):
            t = threading.Thread(target=self._stop_process, args=(p, ))
            t.start()

    def _stop_process(self, process):
        """Stop the process: SIGTERM, and after 5 seconds, SIGKILL

        Note that on windows, both terminate and kill are effectively
        the same operation."""
        process.terminate()
        for i in range(10):
            if process.poll() is not None:
                return
            time.sleep(0.5)
        process.kill()

    def make_key(self, handler):
        return handler.ctx.execution_id


def _resume_stuck_executions():
    """Resume executions that were in the STARTED state.

    This runs after the mgmtworker has started, and will find and resume
    all executions that are in the STARTED state, which would otherwise
    become stuck.

    For every tenant, query the executions, and for every execution in
    STARTED state, resume it.

    This uses the admin token.
    """
    admin_api_token = get_admin_api_token()
    rest_client = get_rest_client(tenant='default_tenant',
                                  api_token=admin_api_token)
    tenants = rest_client.tenants.list()
    for tenant in tenants:
        tenant_client = get_rest_client(tenant=tenant.name,
                                        api_token=admin_api_token)
        try:
            for execution in tenant_client.executions.list(
                    status=ExecutionState.STARTED):
                try:
                    tenant_client.executions.resume(execution.id)
                except CloudifyClientError as e:
                    logger.warning('Could not resume execution {0} on '
                                   'tenant {1}: {2}'
                                   .format(execution.id, tenant.name, e))
                else:
                    logger.info('Resuming execution {0} on tenant {1}'
                                .format(execution.id, tenant.name))
        except (ExpiredCloudifyLicense, MissingCloudifyLicense):
            logger.warning('No valid Cloudify license, could not resume'
                           ' executions.')


def make_amqp_worker(args):
    operation_registry = ProcessRegistry()
    workflow_registry = ProcessRegistry()
    handlers = [
        CloudifyOperationConsumer(args.queue, args.max_workers,
                                  registry=operation_registry),
        CloudifyWorkflowConsumer(args.queue, args.max_workers,
                                 registry=workflow_registry),
        ServiceTaskConsumer(args.name, args.queue, args.max_workers,
                            operation_registry=operation_registry,
                            workflow_registry=workflow_registry),
    ]

    if args.hooks_queue:
        handlers.append(HookConsumer(args.hooks_queue,
                                     registry=operation_registry,
                                     max_workers=args.max_workers))

    return AMQPConnection(handlers=handlers, name=args.name,
                          connect_timeout=None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue')
    parser.add_argument('--max-workers', default=DEFAULT_MAX_WORKERS, type=int)
    parser.add_argument('--name')
    parser.add_argument('--hooks-queue')
    args = parser.parse_args()

    if args.name:
        _setup_excepthook(args.name)
    _setup_logger(args.name)
    if not args.name:
        _resume_stuck_executions()
    worker = make_amqp_worker(args)
    worker.consume()


if __name__ == '__main__':
    main()
