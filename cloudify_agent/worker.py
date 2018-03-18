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

import pika
from pika.exceptions import AMQPConnectionError

from cloudify import dispatch, broker_config

D_CONN_ATTEMPTS = 12
D_RETRY_DELAY = 5
BROKER_PORT_SSL = 5671
BROKER_PORT_NO_SSL = 5672


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

        # result = self.channel.queue_declare(
        #     auto_delete=True,
        #     durable=False,
        #     exclusive=False)
        # queue = result.method.queue
        self.channel.basic_qos(prefetch_size=1)
        self.channel.queue_bind(queue=queue,
                                exchange=queue,
                                routing_key='')
        self.channel.basic_consume(self._process, queue)

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
        parsed_body = json.loads(body)
        logger.info(parsed_body)
        result = None
        task = parsed_body['cloudify_task']
        try:
            kwargs = task['kwargs']
            rv = dispatch.dispatch(**kwargs)
            result = {'ok': True, 'id': parsed_body['id'], 'result': rv}
        except Exception as e:
            logger.warn('Failed message processing: {0!r}'.format(e))
            logger.warn('Body: {0}\nType: {1}'.format(body, type(body)))
            result = {'ok': False, 'error': repr(e), 'id': parsed_body['id']}
        finally:
            logger.info('response %r', result)
            self.channel.basic_publish(
                self.result_exchange, parsed_body['id'], json.dumps(result)
            )
            self.channel.basic_ack(method.delivery_tag)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue')
    args = parser.parse_args()
    consumer = AMQPTopicConsumer(queue=args.queue)
    consumer.consume()


if __name__ == '__main__':
    main()
