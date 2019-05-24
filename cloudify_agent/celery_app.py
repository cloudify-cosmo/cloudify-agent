########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

import os
from cloudify import broker_config
from cloudify.utils import internal
from cloudify.constants import (CELERY_TASK_RESULT_EXPIRES,
                                MGMTWORKER_QUEUE,
                                BROKER_PORT_SSL,
                                BROKER_PORT_NO_SSL)


def get_celery_app(broker_url=None,
                   broker_ssl_cert_path=None,
                   broker_ssl_enabled=None,
                   max_retries=3,
                   tenant=None,
                   target=None):
    """
    Return a Celery app

    :param broker_url: If supplied, will be used as the broker URL
    :param broker_ssl_cert_path: If not supplied, default is in broker_config
    :param broker_ssl_enabled: Decides whether SSL should be enabled
    :param tenant: If supplied, and if target isn't the mgmtworker queue,
    the broker URL will be derived from the data kept in it
    :param target: The target queue; see `tenant`
    :param max_retries:
    :return: A celery.Celery object
    """
    # celery is imported locally since it's not used by any other method, and
    # we want this utils module to be usable even if celery is not available
    from celery import Celery

    if broker_ssl_enabled is None:
        broker_ssl_enabled = broker_config.broker_ssl_enabled

    broker_url = broker_url or _get_broker_url(tenant,
                                               target,
                                               broker_ssl_enabled)
    broker_ssl_options = internal.get_broker_ssl_options(
        ssl_enabled=broker_ssl_enabled,
        cert_path=broker_ssl_cert_path or broker_config.broker_cert_path
    )

    celery_client = Celery()
    celery_client.conf.update(
        BROKER_URL=broker_url,
        CELERY_RESULT_BACKEND=broker_url,
        BROKER_USE_SSL=broker_ssl_options,
        CELERY_TASK_RESULT_EXPIRES=CELERY_TASK_RESULT_EXPIRES
    )

    # Connect eagerly to error out as early as possible, and to force choosing
    # the broker if multiple urls were passed.
    # If max_retries is provided and >0, we will raise an exception if we
    # can't connect; otherwise we'll keep retrying forever.
    # Need to raise an exception in the case of a cluster, so that the
    # next node can be tried
    celery_client.pool.connection.ensure_connection(max_retries=max_retries)
    return celery_client


def _broker_options():
    heartbeat = broker_config.broker_heartbeat
    if heartbeat and os.name != 'nt':
        return '?heartbeat={0}'.format(heartbeat)
    else:
        return ''


URL_TEMPLATE = \
    'amqp://{username}:{password}@{hostname}:{port}/{vhost}{options}'


def _get_broker_url(tenant, target, broker_ssl_enabled):
    """
    If the target is the mgmtworker queue, or if no tenants was passed use
    the default broker URL. Otherwise, create a tenant-specific one
    """
    if target == MGMTWORKER_QUEUE or not tenant:
        port = BROKER_PORT_SSL if broker_ssl_enabled else BROKER_PORT_NO_SSL
        options = _broker_options()
        return ';'.join(
            URL_TEMPLATE.format(
                username=broker_config.broker_username,
                password=broker_config.broker_hostname,
                hostname=hostname,
                port=port,
                vhost=broker_config.broker_vhost,
                options=options
            ) for hostname in broker_config.broker_hostname)

    else:
        return _get_tenant_broker_url(tenant, broker_ssl_enabled)


def _get_tenant_broker_url(tenant, broker_ssl_enabled):
    port = BROKER_PORT_SSL if broker_ssl_enabled else BROKER_PORT_NO_SSL
    options = _broker_options()
    return ';'.join(
        URL_TEMPLATE.format(
            username=tenant['rabbitmq_username'],
            password=tenant['rabbitmq_password'],
            hostname=hostname,
            port=port,
            vhost=tenant['rabbitmq_vhost'],
            options=options
        ) for hostname in broker_config.broker_hostname)
