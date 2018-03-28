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
import json
import time
import argparse
import logging
import logging.handlers
from threading import Thread, Lock

import pika
from pika.exceptions import AMQPConnectionError

from cloudify import dispatch, broker_config
from cloudify.utils import store_execution, delete_execution_dir, get_execution, WORKFLOWS_DIR  # NOQA


D_CONN_ATTEMPTS = 12
D_RETRY_DELAY = 5
BROKER_PORT_SSL = 5671
BROKER_PORT_NO_SSL = 5672

LOGFILE_BACKUP_COUNT = 5
LOGFILE_SIZE_BYTES = 5 * 1024 * 1024

DEFAULT_MAX_WORKERS = 10

CONSUMER_LOCK = Lock()


class AMQPTopicConsumer(object):

    def __init__(self, queue, max_workers, log_file, log_level):
        """
            AMQPTopicConsumer initialisation expects a connection_parameters
            dict as provided by the __main__ of amqp_influx.
        """
        self.queue = queue
        self._max_workers = max_workers
        self.result_exchange = '{0}_result'.format(queue)

        self.connection = self._get_connection()

        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=queue,
                                   durable=True,
                                   auto_delete=False)

        for exchange in [self.queue, self.result_exchange]:
            self.channel.exchange_declare(
                exchange=exchange,
                type='direct',
                auto_delete=False,
                durable=True)

        self.channel.basic_qos(prefetch_count=max_workers)
        self.channel.queue_bind(queue=queue,
                                exchange=queue,
                                routing_key='')
        self.channel.basic_consume(self._process, queue)
        self._thread_pool = []
        self._logger = _init_logger(log_file, log_level)

    @staticmethod
    def _get_connection_params():
        credentials = pika.credentials.PlainCredentials(
            username=broker_config.broker_username,
            password=broker_config.broker_password,
        )
        return pika.ConnectionParameters(
            host=broker_config.broker_hostname,
            port=broker_config.broker_port,
            virtual_host=broker_config.broker_vhost,
            credentials=credentials,
            ssl=broker_config.broker_ssl_enabled,
            ssl_options=broker_config.broker_ssl_options
        )

    def _get_connection(self):
        connection_params = self._get_connection_params()

        # add retry with try/catch because Pika is currently ignoring these
        # connection parameters when using BlockingConnection:
        # https://github.com/pika/pika/issues/354
        for _ in range(D_CONN_ATTEMPTS):
            try:
                connection = pika.BlockingConnection(connection_params)
            except AMQPConnectionError:
                time.sleep(D_RETRY_DELAY)
            else:
                break
        else:
            raise AMQPConnectionError

        return connection

    def consume(self):
        t = Thread(target=self._process_stored)
        t.daemon = True
        t.start()
        self.channel.start_consuming()

    def _process_stored(self):
        try:
            stored = os.listdir(WORKFLOWS_DIR)
        except OSError:
            self._logger.warn('no stored')
            return
        self._logger.warn('stored: {0}'.format(stored))
        for execution_id in stored:
            try:
                e = get_execution(execution_id)
            except IOError:
                continue
            self._logger.warn('processing {0}'.format(execution_id))
            self._do_dispatch(e['task']['kwargs'], e['reply_to'],
                              e['correlation_id'])
            delete_execution_dir(execution_id)
            self._logger.warn('done processing {0}'.format(execution_id))

    def _process(self, channel, method, properties, body):
        # Clear out finished threads
        self._thread_pool = [t for t in self._thread_pool if t.is_alive()]

        if len(self._thread_pool) <= self._max_workers:
            new_thread = Thread(
                target=self._process_message,
                args=(channel, method, properties, body)
            )
            self._thread_pool.append(new_thread)
            new_thread.daemon = True
            new_thread.start()

    def _process_message(self, channel, method, properties, body):
        parsed_body = json.loads(body)
        self._logger.info(parsed_body)
        task = parsed_body['cloudify_task']
        execution_id = None
        try:
            context = task['kwargs']['__cloudify_context']
            if context['type'] == 'workflow':
                execution_id = context['execution_id']
        except KeyError:
            raise
        else:
            if execution_id:
                store_execution(execution_id, {
                    'task': task,
                    'correlation_id': properties.correlation_id,
                    'reply_to': properties.reply_to
                })

        channel.basic_ack(method.delivery_tag)
        self._do_dispatch(task['kwargs'], properties.reply_to,
                          properties.correlation_id)
        if execution_id:
            delete_execution_dir(execution_id)

    def _do_dispatch(self, kwargs, reply_to, correlation_id):
        try:
            rv = dispatch.dispatch(**kwargs)
            result = {'ok': True, 'result': rv}
        except Exception as e:
            self._logger.warn('Failed message processing: {0!r}'.format(e))
            self._logger.warn('Kwargs: {0}'.format(kwargs))
            result = {'ok': False, 'error': repr(e)}
        finally:

            self._logger.info('response %r', result)
            with CONSUMER_LOCK:
                if reply_to:
                    self.channel.basic_publish(
                        exchange='',
                        routing_key=reply_to,
                        properties=pika.BasicProperties(
                            correlation_id=correlation_id),
                        body=json.dumps(result)
                    )


def _init_logger(log_file, log_level):
    logger = logging.getLogger(__name__)
    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=LOGFILE_SIZE_BYTES,
        backupCount=LOGFILE_BACKUP_COUNT
    )
    handler.setLevel(log_level)
    logger.addHandler(handler)
    logger.setLevel(log_level)
    return logger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue')
    parser.add_argument('--max-workers', default=DEFAULT_MAX_WORKERS, type=int)
    parser.add_argument('--log-file')
    parser.add_argument('--log-level', default='INFO')
    args = parser.parse_args()
    consumer = AMQPTopicConsumer(
        queue=args.queue,
        max_workers=args.max_workers,
        log_file=args.log_file,
        log_level=args.log_level
    )
    consumer.consume()


if __name__ == '__main__':
    main()
