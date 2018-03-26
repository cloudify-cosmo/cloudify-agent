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
import logging
import argparse
from threading import Thread

import pika
from pika.exceptions import AMQPConnectionError

from cloudify import dispatch, broker_config

D_CONN_ATTEMPTS = 12
D_RETRY_DELAY = 5
BROKER_PORT_SSL = 5671
BROKER_PORT_NO_SSL = 5672

# TODO: Make it configurable and scalable
MAX_NUM_OF_WORKERS = 3


# TODO: Properly handle logging (write to file, etc)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()


class AMQPTopicConsumer(object):

    def __init__(self, queue):
        """
            AMQPTopicConsumer initialisation expects a connection_parameters
            dict as provided by the __main__ of amqp_influx.
        """
        self.queue = queue
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

        self.channel.basic_qos(prefetch_count=1)
        self.channel.queue_bind(queue=queue,
                                exchange=queue,
                                routing_key='')
        self.channel.basic_consume(self._process, queue)
        self._thread_pool = []

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
        self.channel.start_consuming()

    def _process(self, channel, method, properties, body):
        # Clear out finished threads
        self._thread_pool = [t for t in self._thread_pool if t.is_alive()]

        if len(self._thread_pool) <= MAX_NUM_OF_WORKERS:
            new_thread = Thread(
                target=_process_message,
                args=(channel, method, properties, body)
            )
            self._thread_pool.append(new_thread)
            new_thread.daemon = True
            new_thread.start()


def _process_message(channel, method, properties, body):
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
            channel.basic_publish(
                exchange='',
                routing_key=properties.reply_to,
                properties=pika.BasicProperties(
                    correlation_id=properties.correlation_id),
                body=json.dumps(result)
            )
        channel.basic_ack(method.delivery_tag)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue')
    args = parser.parse_args()
    consumer = AMQPTopicConsumer(queue=args.queue)
    consumer.consume()


if __name__ == '__main__':
    main()
