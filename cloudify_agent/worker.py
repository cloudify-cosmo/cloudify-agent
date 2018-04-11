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
import Queue
import argparse
import logging
import logging.handlers
from threading import Thread

import pika
from pika.exceptions import ConnectionClosed

from cloudify import exceptions, dispatch, broker_config
from cloudify.error_handling import serialize_known_exception

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

    def __init__(self, queue, max_workers, log_file, log_level):
        self.queue = queue
        self._max_workers = max_workers
        self._thread_pool = []
        self._logger = _init_logger(log_file, log_level)
        self._publish_queue = Queue.Queue()

    # the public methods consume and publish are threadsafe
    def _connect(self):
        self.connection = pika.BlockingConnection(
            self._get_connection_params()
        )
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
            ssl_options=broker_config.broker_ssl_options,
            heartbeat=HEARTBEAT_INTERVAL,
            connection_attempts=D_CONN_ATTEMPTS,
            retry_delay=D_RETRY_DELAY
        )

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

    def _process_message(self, properties, body):
        parsed_body = json.loads(body)
        self._logger.info(parsed_body)
        result = None
        task = parsed_body['cloudify_task']
        try:
            kwargs = task['kwargs']
            rv = dispatch.dispatch(**kwargs)
            result = {'ok': True, 'result': rv}
            self._logger.warning(task)
            self._logger.info('SUCCESS - result: {0}'.format(result))
        except SUPPORTED_EXCEPTIONS as e:
            error = serialize_known_exception(e)
            result = {'ok': False, 'error': error}
            self._logger.error(
                'ERROR - caught: {0}\n{1}'.format(
                    repr(e), error['traceback']
                )
            )
        except Exception as e:
            result = {'ok': False, 'error': repr(e)}
            self._logger.error(
                'ERROR - failed message processing: '
                '{0!r}\nbody: {1}\ntype: {2}'.format(e, body, type(body))
            )
        finally:
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
