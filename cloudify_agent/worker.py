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
import time
import logging
import argparse
import traceback
import threading

from cloudify_agent.api import utils
from cloudify_agent.api.factory import DaemonFactory

from cloudify_rest_client.exceptions import UserUnauthorizedError

from cloudify import constants, dispatch, exceptions, state
from cloudify.models_states import ExecutionState
from cloudify.logs import setup_agent_logger
from cloudify.state import current_ctx
from cloudify.error_handling import serialize_known_exception
from cloudify.amqp_client import AMQPConnection, TaskConsumer, NO_RESPONSE
from cloudify.utils import get_manager_name
from cloudify_agent.operations import install_plugins, uninstall_plugins

DEFAULT_MAX_WORKERS = 10


class CloudifyOperationConsumer(TaskConsumer):
    routing_key = 'operation'
    handler = dispatch.OperationHandler

    def __init__(self, *args, **kwargs):
        self._registry = kwargs.pop('registry')
        super(CloudifyOperationConsumer, self).__init__(*args, **kwargs)

    def _print_task(self, ctx, action, handler, status=None):
        with state.current_ctx.push(handler.ctx):
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
                '\n\t%(prefix)s on queue `%(queue)s` on tenant `%(tenant)s`:\n'
                '\tTask name: %(name)s\n'
                '\tExecution ID: %(execution_id)s\n'
                '\tWorkflow ID: %(workflow_id)s%(suffix)s\n',
                {'tenant': tenant_name,
                 'prefix': prefix,
                 'name': ctx['task_name'],
                 'queue': ctx.get('task_target'),
                 'execution_id': ctx.get('execution_id'),
                 'workflow_id': ctx.get('workflow_id'),
                 'suffix': suffix})

    @staticmethod
    def _validate_not_cancelled(handler, ctx):
        """
        This method will validate if the current running tasks is cancelled
        or not
        :param handler:
        :param ctx:
        """
        # We need also to handle old tasks still in queue and not picked by
        # the worker so that we can ignore them as the state of the
        # execution is cancelled and ignore pending tasks picked by the
        # worker but still not executed. Morever,we need to handle a case when
        # resume workflow is running while there are some old operations
        # tasks still in the queue which holds an invalid execution token
        # which could raise 401 error
        # Need to use the context associated with the that task
        with state.current_ctx.push(handler.ctx):
            try:
                # Get the status of the current execution so that we can
                # tell if the current running task can be run or not
                current_execution = handler.ctx.get_execution(
                    ctx.get('execution_id')
                )
                if current_execution:
                    logger.info(
                        'The current status of the execution is {0}'
                        ''.format(current_execution.status)
                    )
                    # If the current execution task is cancelled, that means
                    # some this current task was on the queue when the previous
                    # cancel operation triggered, so we need to ignore running
                    # such tasks from the previous execution which was
                    # cancelled
                    if current_execution.status == ExecutionState.CANCELLED:
                        raise exceptions.ProcessKillCancelled()
                else:
                    raise exceptions.NonRecoverableError(
                        'No execution available'
                    )
            except UserUnauthorizedError:
                # This means that Execution token is no longer valid since
                # there is a new token re-generated because of resume workflow
                raise exceptions.ProcessKillCancelled()

    def handle_task(self, full_task):
        task = full_task['cloudify_task']
        ctx = task['kwargs'].pop('__cloudify_context')

        handler = self.handler(cloudify_context=ctx,
                               args=task.get('args', []),
                               kwargs=task['kwargs'],
                               process_registry=self._registry)

        self._print_task(ctx, 'Started handling', handler)
        try:
            self._validate_not_cancelled(handler, ctx)
            rv = handler.handle_or_dispatch_to_subprocess_if_remote()
            result = {'ok': True, 'result': rv}
            status = 'SUCCESS - result: {0}'.format(result)
        except exceptions.ProcessKillCancelled:
            self._print_task(ctx, 'Task kill-cancelled', handler)
            return NO_RESPONSE
        except Exception as e:
            error = serialize_known_exception(e)
            result = {'ok': False, 'error': error}
            status = 'ERROR - result: {0}'.format(result)
            logger.error(
                'ERROR - caught: {0}\n{1}'.format(
                    repr(e), error['traceback']))
        self._print_task(ctx, 'Finished handling', handler, status)
        return result


class ServiceTaskConsumer(TaskConsumer):
    routing_key = 'service'
    service_tasks = {
        'ping': 'ping_task',
        'cluster-update': 'cluster_update_task',
        'cancel-operation': 'cancel_operation_task',
        'replace-ca-certs': 'replace_ca_certs_task',
        'install-plugin': 'install_plugin_task',
        'uninstall-plugin': 'uninstall_plugin_task',
    }

    def __init__(self, name, *args, **kwargs):
        self.name = name
        self._operation_registry = kwargs.pop('operation_registry')
        super(ServiceTaskConsumer, self).__init__(*args, **kwargs)

    def handle_task(self, full_task):

        task = full_task['service_task']
        task_name = task['task_name']
        kwargs = task['kwargs']

        logger.info(
            'Received `{0}` service task with kwargs: {1}'.format(
                task_name, kwargs))
        task_handler = getattr(self, self.service_tasks[task_name])
        result = task_handler(**kwargs)
        logger.info('Result: {0}'.format(result))
        return result

    def ping_task(self):
        return {'time': time.time()}

    def install_plugin_task(self, plugin, rest_token, tenant,
                            rest_host, target=None, bypass_maintenance=False):

        if target:
            # target was provided, so this is to be installed only on the
            # specified workers, but might have been received by us because
            # it was sent to a fanout exchange.
            # This only matters for mgmtworkers, because agents have no
            # fanout exchanges.
            if get_manager_name() not in target:
                return

        class _EmptyID(object):
            id = None

        class PluginInstallCloudifyContext(object):
            """A CloudifyContext that has just enough data to install plugins
            """
            def __init__(self):
                self.rest_host = rest_host
                self.tenant_name = tenant['name']
                self.rest_token = rest_token
                self.execution_token = None
                self.logger = logging.getLogger('plugin')
                # deployment/blueprint are not defined for force-installs,
                # but the ctx demands they be objects with an .id
                self.deployment = _EmptyID()
                self.blueprint = _EmptyID()
                self.bypass_maintenance = bypass_maintenance

        with current_ctx.push(PluginInstallCloudifyContext()):
            install_plugins([plugin])

    def uninstall_plugin_task(self, plugin, rest_token, tenant,
                              rest_host, target=None,
                              bypass_maintenance=False):

        if target:
            # target was provided, so this is to be installed only on the
            # specified workers, but might have been received by us because
            # it was sent to a fanout exchange.
            # This only matters for mgmtworkers, because agents have no
            # fanout exchanges.
            if get_manager_name() not in target:
                return

        class _EmptyID(object):
            id = None

        class PluginUninstallCloudifyContext(object):
            """A CloudifyContext that has just enough data to uninstall plugins
            """
            def __init__(self):
                self.rest_host = rest_host
                self.tenant_name = tenant['name']
                self.rest_token = rest_token
                self.execution_token = None
                self.logger = logging.getLogger('plugin')
                # deployment/blueprint are not defined for force-installs,
                # but the ctx demands they be objects with an .id
                self.deployment = _EmptyID()
                self.blueprint = _EmptyID()
                self.bypass_maintenance = bypass_maintenance

        with current_ctx.push(PluginUninstallCloudifyContext()):
            uninstall_plugins([plugin])

    def cluster_update_task(self, brokers, broker_ca, managers, manager_ca):
        """Update the running agent with the new cluster.

        When a node is added or removed from the cluster, the agent will
        receive the current cluster nodes in this task. We need to update
        both the current process envvars, the cert files, and all the
        daemon config files.
        """
        self._assert_name('cluster-update')
        factory = DaemonFactory()
        daemon = factory.load(self.name)

        os.environ[constants.REST_HOST_KEY] = \
            u','.join(managers).encode('utf-8')

        with open(daemon.local_rest_cert_file, 'w') as f:
            f.write(manager_ca)
        with open(daemon.broker_ssl_cert_path, 'w') as f:
            f.write(broker_ca)

        daemon.rest_host = managers
        daemon.broker_ip = brokers
        daemon.create_broker_conf()
        daemon.create_config()

        factory.save(daemon)

    def cancel_operation_task(self, execution_id):
        logger.info('Cancelling task {0}'.format(execution_id))
        self._operation_registry.cancel(execution_id)

    def replace_ca_certs_task(self, new_manager_ca, new_broker_ca):
        """Update the running agent with new CAs."""
        self._assert_name('replace-ca-certs')
        factory = DaemonFactory()
        daemon = factory.load(self.name)

        if new_broker_ca:
            with open(daemon.broker_ssl_cert_path, 'w') as f:
                f.write(new_broker_ca)
            daemon.create_broker_conf()

        if new_manager_ca:
            with open(daemon.local_rest_cert_file, 'w') as f:
                f.write(new_manager_ca)
            daemon.create_config()

        factory.save(daemon)

    def _assert_name(self, command_name):
        if not self.name:
            raise RuntimeError('{0} sent to agent with no name '
                               'set'.format(command_name))


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
        self._cancelled = set()

    def register(self, handler, process):
        self._processes.setdefault(self.make_key(handler), []).append(process)

    def unregister(self, handler, process):
        key = self.make_key(handler)
        try:
            self._processes[key].remove(process)
        except (KeyError, ValueError):
            pass
        if not self._processes[key] and key in self._cancelled:
            self._cancelled.remove(key)

    def cancel(self, task_id):
        self._cancelled.add(task_id)
        threads = [
            threading.Thread(target=self._stop_process, args=(p,))
            for p in self._processes.get(task_id, [])
        ]
        for thread in threads:
            thread.start()

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

    def is_cancelled(self, handler):
        return self.make_key(handler) in self._cancelled

    def make_key(self, handler):
        return handler.ctx.execution_id


def make_amqp_worker(args):
    operation_registry = ProcessRegistry()
    handlers = [
        CloudifyOperationConsumer(args.queue, args.max_workers,
                                  registry=operation_registry),
        ServiceTaskConsumer(args.name, args.queue, args.max_workers,
                            operation_registry=operation_registry),
    ]

    return AMQPConnection(handlers=handlers,
                          name=args.name,
                          connect_timeout=None)


def main():
    global logger

    parser = argparse.ArgumentParser()
    parser.add_argument('--queue')
    parser.add_argument('--max-workers', default=DEFAULT_MAX_WORKERS, type=int)
    parser.add_argument('--name')
    parser.add_argument('--hooks-queue')
    args = parser.parse_args()

    if args.name:
        _setup_excepthook(args.name)
    logger = logging.getLogger('worker.{0}'.format(args.name))
    setup_agent_logger(args.name)

    worker = make_amqp_worker(args)
    worker.consume()


if __name__ == '__main__':
    main()
