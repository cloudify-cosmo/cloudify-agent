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

import json
import time
import Queue
import argparse
import logging
import logging.handlers
from threading import Thread, Semaphore

import pika
from pika.exceptions import ConnectionClosed

from cloudify import broker_config, dispatch, exceptions
from cloudify.error_handling import serialize_known_exception
from cloudify_agent.api.factory import DaemonFactory


HEARTBEAT_INTERVAL = 30
D_CONN_ATTEMPTS = 12
D_RETRY_DELAY = 5
BROKER_PORT_SSL = 5671
BROKER_PORT_NO_SSL = 5672

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


class AMQPWorker(object):
    def __init__(self, handlers, logger, name=None):
        self._logger = logger
        self._handlers = handlers
        self._publish_queue = Queue.Queue()
        self.name = name
        self._connection_params = self._get_connection_params()

    def _get_common_connection_params(self):
        credentials = pika.credentials.PlainCredentials(
            username=broker_config.broker_username,
            password=broker_config.broker_password,
        )
        return {
            'host': broker_config.broker_hostname,
            'port': broker_config.broker_port,
            'virtual_host': broker_config.broker_vhost,
            'credentials': credentials,
            'ssl': broker_config.broker_ssl_enabled,
            'ssl_options': broker_config.broker_ssl_options,
            'heartbeat': HEARTBEAT_INTERVAL
        }

    def _get_connection_params(self):
        while True:
            params = self._get_common_connection_params()
            if self.name:
                daemon = DaemonFactory().load(self.name)
                if daemon.cluster:
                    for node_ip in daemon.cluster:
                        params['host'] = node_ip
                        yield pika.ConnectionParameters(**params)
                    continue
            yield pika.ConnectionParameters(**params)

    def _connect(self):
        params = next(self._connection_params)
        self.connection = pika.BlockingConnection(params)
        out_channel = self.connection.channel()
        for handler in self._handlers:
            handler.register(self.connection, self._publish_queue)
            self._logger.info('Registered handler for {0}'
                              .format(handler.routing_key))
        return out_channel

    def consume(self):
        out_channel = self._connect()
        while True:
            try:
                self.connection.process_data_events(0.2)
                self._process_publish(out_channel)
            except ConnectionClosed:
                out_channel = self._connect()
                continue

    def _process_publish(self, channel):
        while True:
            try:
                msg = self._publish_queue.get_nowait()
            except Queue.Empty:
                return
            try:
                channel.basic_publish(**msg)
            except ConnectionClosed:
                # if we couldn't send the message because the connection
                # was down, requeue it to be sent again later
                self._publish_queue.put(msg)
                raise


class TaskConsumer(object):
    routing_key = ''

    def __init__(self, queue, logger, threadpool_size=5):
        self.threadpool_size = threadpool_size
        self.exchange = queue
        self.queue = '{0}_{1}'.format(queue, self.routing_key)
        self._logger = logger
        self._sem = Semaphore(threadpool_size)
        self._output_queue = None

    def register(self, connection, output_queue):
        self._output_queue = output_queue

        in_channel = connection.channel()
        in_channel.basic_qos(prefetch_count=self.threadpool_size)
        in_channel.exchange_declare(
            exchange=self.queue, auto_delete=False, durable=True)
        in_channel.queue_declare(queue=self.queue,
                                 durable=True,
                                 auto_delete=False)
        in_channel.queue_bind(queue=self.queue,
                              exchange=self.exchange,
                              routing_key=self.routing_key)
        in_channel.basic_consume(self.process, self.queue)

    def process(self, channel, method, properties, body):
        try:
            full_task = json.loads(body)
        except ValueError:
            self._logger.error('Error parsing task: {0}'.format(body))
            return

        self._sem.acquire()
        new_thread = Thread(
            target=self._process_message,
            args=(properties, full_task)
        )
        new_thread.daemon = True
        new_thread.start()
        channel.basic_ack(method.delivery_tag)

    def _process_message(self, properties, full_task):
        try:
            result = self.handle_task(full_task)
        except Exception as e:
            result = {'ok': False, 'error': repr(e)}
            self._logger.error(
                'ERROR - failed message processing: '
                '{0!r}\nbody: {1}'.format(e, full_task)
            )

        if properties.reply_to:
            self._output_queue.put({
                'exchange': '',
                'routing_key': properties.reply_to,
                'properties': pika.BasicProperties(
                    correlation_id=properties.correlation_id),
                'body': json.dumps(result)
            })
        self._sem.release()

    def handle_task(self, full_task):
        raise NotImplementedError()


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
