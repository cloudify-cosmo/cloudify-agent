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
from pika.exceptions import AMQPConnectionError, ConnectionClosed

from cloudify import dispatch, broker_config

D_CONN_ATTEMPTS = 12
D_RETRY_DELAY = 5
BROKER_PORT_SSL = 5671
BROKER_PORT_NO_SSL = 5672

LOGFILE_BACKUP_COUNT = 5
LOGFILE_SIZE_BYTES = 5 * 1024 * 1024

DEFAULT_MAX_WORKERS = 10


class AMQPWorker(object):

    def __init__(self, queue, max_workers, log_file, log_level):
        self.queue = queue
        self._max_workers = max_workers
        self._thread_pool = []
        self._logger = _init_logger(log_file, log_level)
        self._publish_queue = Queue.Queue()

    # the public methods consume and publish are threadsafe
    def _connect(self):
        self.connection = self._get_connection()
        in_channel = self.connection.channel()
        out_channel = self.connection.channel()

        in_channel.basic_qos(prefetch_count=self._max_workers)
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
                target=_process_message,
                args=(self, channel, properties, body, self._logger)
            )
            self._thread_pool.append(new_thread)
            new_thread.daemon = True
            new_thread.start()

        channel.basic_ack(method.delivery_tag)


def _process_message(worker, channel, properties, body, logger):
    parsed_body = json.loads(body)
    logger.info(parsed_body)
    result = None
    task = parsed_body['cloudify_task']
    try:
        kwargs = task['kwargs']
        rv = dispatch.dispatch(**kwargs)
        result = {'ok': True, 'result': rv}
    except Exception as e:
        logger.warn('Failed message processing: {0!r}'.format(e))
        logger.warn('Body: {0}\nType: {1}'.format(body, type(body)))
        result = {'ok': False, 'error': repr(e)}
    finally:
        logger.info('response %r', result)
        if properties.reply_to:
            worker.publish(
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
    consumer = AMQPWorker(
        queue=args.queue,
        max_workers=args.max_workers,
        log_file=args.log_file,
        log_level=args.log_level
    )
    consumer.consume()


if __name__ == '__main__':
    main()
