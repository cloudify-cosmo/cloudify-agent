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

import time
import argparse
import logging
import logging.handlers


from cloudify import dispatch, exceptions
from cloudify.amqp_client import AMQPWorker, TaskConsumer
from cloudify.error_handling import serialize_known_exception
from cloudify_agent.api.factory import DaemonFactory


LOGFILE_BACKUP_COUNT = 5
LOGFILE_SIZE_BYTES = 5 * 1024 * 1024

DEFAULT_MAX_WORKERS = 10

SUPPORTED_EXCEPTIONS = (
    exceptions.OperationRetry,
    exceptions.RecoverableError,
    exceptions.NonRecoverableError,
    exceptions.ProcessExecutionError,
    exceptions.HttpException
)


class CloudifyOperationConsumer(TaskConsumer):
    routing_key = 'operation'
    handler = dispatch.OperationHandler

    def _print_task(self, task):
        ctx = task['cloudify_task']['kwargs']['__cloudify_context']
        if ctx['type'] == 'workflow':
            prefix = 'Processing workflow'
            suffix = ''
        else:
            prefix = 'Processing operation'
            suffix = '\nNode ID: {0}'.format(ctx['node_id'])
        self._logger.info(
            '{prefix} on queue `{queue}` on tenant `{tenant}`:\n'
            'Task name: {name}\n'
            'Execution ID: {execution_id}\n'
            'Workflow ID: {workflow_id}{suffix}'.format(
                prefix=prefix,
                name=ctx['task_name'],
                queue=ctx['task_target'],
                tenant=ctx['tenant']['name'],
                execution_id=ctx['execution_id'],
                workflow_id=ctx['workflow_id'],
                suffix=suffix
            )
        )

    def handle_task(self, full_task):
        self._print_task(full_task)
        result = None
        task = full_task['cloudify_task']
        ctx = task['kwargs'].pop('__cloudify_context')
        handler = self.handler(cloudify_context=ctx, args=task.get('args', []),
                               kwargs=task['kwargs'])
        try:
            rv = handler.handle_or_dispatch_to_subprocess_if_remote()
            result = {'ok': True, 'result': rv}
            self._logger.info('SUCCESS - result: {0}'.format(result))
        except SUPPORTED_EXCEPTIONS as e:
            error = serialize_known_exception(e)
            result = {'ok': False, 'error': error}
            self._logger.error(
                'ERROR - caught: {0}\n{1}'.format(
                    repr(e), error['traceback']
                )
            )
        return result


class CloudifyWorkflowConsumer(CloudifyOperationConsumer):
    routing_key = 'workflow'
    handler = dispatch.WorkflowHandler


class ServiceTaskConsumer(TaskConsumer):
    routing_key = 'service'

    def handle_task(self, full_task):
        service_tasks = {
            'ping': self.ping_task,
            'cluster-update': self.cluster_update_task
        }

        task = full_task['service_task']
        task_name = task['task_name']
        kwargs = task['kwargs']

        return service_tasks[task_name](**kwargs)

    def ping_task(self):
        return {'time': time.time()}

    def cluster_update_task(self, nodes):
        factory = DaemonFactory()
        daemon = factory.load(self.name)
        network_name = daemon.network
        nodes = [n['networks'][network_name] for n in nodes]
        daemon.cluster = nodes
        factory.save(daemon)


def _init_logger(log_file, log_level):
    logger = logging.getLogger(__name__)
    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=LOGFILE_SIZE_BYTES,
        backupCount=LOGFILE_BACKUP_COUNT
    )
    fmt = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setLevel(log_level)
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.setLevel(log_level)
    return logger


def make_amqp_worker(args):
    logger = _init_logger(args.log_file, args.log_level)
    handlers = [
        CloudifyOperationConsumer(args.queue, logger, args.max_workers),
        CloudifyWorkflowConsumer(args.queue, logger, args.max_workers),
        ServiceTaskConsumer(args.queue, logger, args.max_workers),
    ]
    return AMQPWorker(handlers=handlers, logger=logger, name=args.name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue')
    parser.add_argument('--max-workers', default=DEFAULT_MAX_WORKERS, type=int)
    parser.add_argument('--log-file')
    parser.add_argument('--log-level', default='INFO')
    parser.add_argument('--name')
    args = parser.parse_args()
    worker = make_amqp_worker(args)
    worker.consume()


if __name__ == '__main__':
    main()
