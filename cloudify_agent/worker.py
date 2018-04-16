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
from threading import Thread

import pika
from pika.exceptions import ConnectionClosed

from cloudify import broker_config, cluster, dispatch, exceptions
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


def _get_common_connection_params():
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


def _get_connection_params():
    return pika.ConnectionParameters(**_get_common_connection_params())


def _get_agent_connection_params(daemon_name):
    while True:
        params = _get_common_connection_params()
        if cluster.is_cluster_configured():
            nodes = cluster.get_cluster_nodes()
            for node_ip in nodes:
                params['host'] = node_ip
                yield pika.ConnectionParameters(**params)
        else:
            yield pika.ConnectionParameters(**params)


class AMQPWorker(object):

    def __init__(self, connection_params, queue, max_workers,
                 log_file, log_level, name=None):
        self._connection_params = connection_params
        self.queue = queue
        self._max_workers = max_workers
        self._thread_pool = []
        self._logger = _init_logger(log_file, log_level)
        self._publish_queue = Queue.Queue()
        self.name = name

    # the public methods consume and publish are threadsafe
    def _connect(self):
        if isinstance(self._connection_params, pika.ConnectionParameters):
            params = self._connection_params
        else:
            params = next(self._connection_params)

        self.connection = pika.BlockingConnection(params)
        in_channel = self.connection.channel()
        out_channel = self.connection.channel()

        in_channel.basic_qos(prefetch_count=self._max_workers)
        in_channel.exchange_declare(
            exchange=self.queue, auto_delete=False, durable=True)
        in_channel.queue_declare(queue=self.queue,
                                 durable=True,
                                 auto_delete=False)
        in_channel.queue_bind(queue=self.queue,
                              exchange=self.queue,
                              routing_key='')
        in_channel.basic_consume(self._process, self.queue)
        return in_channel, out_channel

    def consume(self):
        in_channel, out_channel = self._connect()
        while True:
            try:
                self.connection.process_data_events(0.2)
                self._process_publish(out_channel)
            except ConnectionClosed:
                in_channel, out_channel = self._connect()
                continue

    def publish(self, **kwargs):
        self._publish_queue.put(kwargs)

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

    def _process(self, channel, method, properties, body):
        # Clear out finished threads
        self._thread_pool = [t for t in self._thread_pool if t.is_alive()]

        if len(self._thread_pool) <= self._max_workers:
            new_thread = Thread(
                target=self._process_message,
                args=(properties, body)
            )
            self._thread_pool.append(new_thread)
            new_thread.daemon = True
            new_thread.start()

        channel.basic_ack(method.delivery_tag)

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

    def _process_cloudify_task(self, full_task):
        self._print_task(full_task)
        result = None
        task = full_task['cloudify_task']
        try:
            kwargs = task['kwargs']
            rv = dispatch.dispatch(**kwargs)
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

    def ping_task(self):
        return {'time': time.time()}

    def cluster_update_task(self, nodes):
        factory = DaemonFactory()
        daemon = factory.load(self.name)
        network_name = daemon.network
        nodes = [n['networks'][network_name] for n in nodes]
        cluster.set_cluster_nodes(nodes)
        daemon.cluster = nodes
        factory.save(daemon)

    def _process_service_task(self, full_task):
        service_tasks = {
            'ping': self.ping_task,
            'cluster-update': self.cluster_update_task
        }

        task = full_task['service_task']
        task_name = task['task_name']
        kwargs = task['kwargs']

        return service_tasks[task_name](**kwargs)

    def _process_message(self, properties, body):
        try:
            full_task = json.loads(body)
        except ValueError:
            self._logger.error('Error parsing task: {0}'.format(body))
            return

        if 'cloudify_task' in full_task:
            handler = self._process_cloudify_task
        elif 'service_task' in full_task:
            handler = self._process_service_task
        else:
            self._logger.error('Could not handle task')
            return

        try:
            result = handler(full_task)
        except Exception as e:
            result = {'ok': False, 'error': repr(e)}
            self._logger.error(
                'ERROR - failed message processing: '
                '{0!r}\nbody: {1}\ntype: {2}'.format(e, body, type(body))
            )

        if properties.reply_to:
            self.publish(
                exchange='',
                routing_key=properties.reply_to,
                properties=pika.BasicProperties(
                    correlation_id=properties.correlation_id),
                body=json.dumps(result)
            )


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue')
    parser.add_argument('--max-workers', default=DEFAULT_MAX_WORKERS, type=int)
    parser.add_argument('--log-file')
    parser.add_argument('--log-level', default='INFO')
    parser.add_argument('--name')
    args = parser.parse_args()

    if args.name:
        # we are an agent
        conn_params = _get_agent_connection_params()
    else:
        # we are the mgmtworker
        conn_params = _get_connection_params()

    consumer = AMQPWorker(
        connection_params=conn_params,
        queue=args.queue,
        max_workers=args.max_workers,
        log_file=args.log_file,
        log_level=args.log_level,
        name=args.name
    )
    consumer.consume()


if __name__ == '__main__':
    main()
