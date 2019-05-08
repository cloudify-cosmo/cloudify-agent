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

from cloudify import dispatch, exceptions
from cloudify.logs import setup_agent_logger
from cloudify.error_handling import serialize_known_exception
from cloudify.amqp_client import AMQPConnection, TaskConsumer

DEFAULT_MAX_WORKERS = 10

SUPPORTED_EXCEPTIONS = (
    exceptions.OperationRetry, exceptions.RecoverableError,
    exceptions.NonRecoverableError, exceptions.ProcessExecutionError,
    exceptions.HttpException)


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
                suffix=suffix))

    def handle_task(self, full_task):
        task = full_task['cloudify_task']
        ctx = task['kwargs'].pop('__cloudify_context')

        self._print_task(ctx, 'Started handling')
        handler = self.handler(cloudify_context=ctx,
                               args=task.get('args', []),
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
                    repr(e), error['traceback']))
        self._print_task(ctx, 'Finished handling', status)
        return result


class ServiceTaskConsumer(TaskConsumer):
    routing_key = 'service'
    service_tasks = {
        'ping': 'ping_task',
        'cluster-update': 'cluster_update_task',
        'cancel-operation': 'cancel_operation_task'
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

    def cluster_update_task(self, nodes):
        # TODO! replace with the add-networks stuff
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
