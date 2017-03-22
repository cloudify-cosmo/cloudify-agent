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

"""
This module is loaded on celery startup. It is not intended to be
used outside the scope of an @operation.
"""
import os
import sys
import getpass
import itertools
import traceback
import tempfile
import logging
import logging.handlers
import kombu.connection

from celery import Celery, signals
from celery.utils.log import ColorFormatter, get_logger
from celery.worker.loops import asynloop
from fasteners import InterProcessLock

from cloudify import cluster
from cloudify.celery import gate_keeper
from cloudify.celery import logging_server

from cloudify_agent.api import exceptions, utils
from cloudify_agent.api.factory import DaemonFactory


logger = get_logger(__name__)
LOGFILE_SIZE_BYTES = 5 * 1024 * 1024
LOGFILE_BACKUP_COUNT = 5


@signals.setup_logging.connect
def setup_logging_handler(loglevel, logfile, format, colorize, **kwargs):
    if logfile:
        if os.name == 'nt':
            logfile = logfile.format(os.getpid())
        handler = logging.handlers.RotatingFileHandler(
            logfile,
            maxBytes=LOGFILE_SIZE_BYTES,
            backupCount=LOGFILE_BACKUP_COUNT)
        handler.setFormatter(logging.Formatter(fmt=format))
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ColorFormatter(fmt=format, use_color=colorize))
    handler.setLevel(loglevel)
    logger = logging.getLogger()
    logger.handlers = []
    logger.addHandler(handler)
    logger.setLevel(loglevel)


@signals.worker_process_init.connect
def declare_fork(**kwargs):
    try:
        import Crypto.Random
        Crypto.Random.atfork()
    except ImportError:
        pass


# This is a ugly hack to restart the hub event loop
# after the Celery mainProcess started...
@signals.worker_ready.connect
def reset_worker_tasks_state(sender, *args, **kwargs):
    if sender.loop is not asynloop:
        return
    inspector = app.control.inspect(destination=[sender.hostname])

    def callback(*args, **kwargs):
        try:
            inspector.stats()
        except:
            pass
    sender.hub.call_soon(callback=callback)


def _cluster_settings_lock(daemon_name):
    return InterProcessLock(
        os.path.join(
            tempfile.gettempdir(),
            'cluster-{0}-{1}.lock'.format(getpass.getuser(), daemon_name)))


# This attribute is used as the celery App instance.
# it is referenced in two ways:
#   1. Celery command line --app options.
#   2. cloudify.dispatch.dispatch uses it as the 'task' decorator.
# For app configuration, see cloudify.broker_config.
app = Celery()
gate_keeper.configure_app(app)
logging_server.configure_app(app)


def _set_master(daemon_name, node):
    factory = DaemonFactory()
    try:
        daemon = factory.load(daemon_name)
    except exceptions.DaemonNotFoundError:
        return
    daemon.broker_ip = node['broker_ip']
    daemon.broker_user = node['broker_user']
    daemon.broker_pass = node['broker_pass']
    daemon.broker_ssl_cert_path = node.get('internal_cert_path')
    with _cluster_settings_lock(daemon_name):
        factory.save(daemon)
        cluster.set_cluster_active(node)


def _make_failover_strategy(daemon_name):
    def _strategy(initial_brokers):
        logger.debug('Failover strategy: searching for a new rabbitmq server')
        initial_brokers = [broker for broker in initial_brokers if broker]
        brokers = itertools.cycle(initial_brokers)
        while True:
            if cluster.is_cluster_configured():
                nodes = cluster.get_cluster_nodes()
                for node in nodes:
                    with _cluster_settings_lock(daemon_name):
                        _set_master(daemon_name, node)

                    ssl_enabled = node.get('broker_ssl_enabled', False)
                    if 'broker_port' in node:
                        port = node['broker_port']
                    else:
                        port = 5671 if ssl_enabled else 5672

                    broker_url = 'amqp://{0}:{1}@{2}:{3}//'.format(
                        node['broker_user'],
                        node['broker_pass'],
                        node['broker_ip'],
                        port)

                    if ssl_enabled:
                        # use a different cert for each node in the cluster -
                        # can't pass that in the amqp url
                        broker_ssl_cert_path = node.get('internal_cert_path')
                        if broker_ssl_cert_path:
                            app.conf['BROKER_USE_SSL']['ca_certs'] =\
                                broker_ssl_cert_path

                    logger.debug('Trying broker at {0}'
                                 .format(broker_url))
                    yield broker_url
            else:
                logger.debug('cluster config file does not exist')
                broker_url = next(brokers)
                if len(initial_brokers) > 1:
                    logger.debug('writing config file')
                    with _cluster_settings_lock(daemon_name):
                        cluster.config_from_broker_urls(broker_url,
                                                        initial_brokers)
                        _set_master(daemon_name, cluster.get_cluster_active())
                logger.debug('Trying broker at {0}'
                             .format(broker_url))
                yield broker_url

    return _strategy


try:
    # running inside an agent
    daemon_name = utils.internal.get_daemon_name()
except KeyError:
    # running outside an agent
    daemon_name = None

if daemon_name:

    # Setting a new exception hook to catch any exceptions
    # on celery startup and write them to a file. This file
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

    kombu.connection.failover_strategies['check_cluster_config'] = \
        _make_failover_strategy(daemon_name)
    app.conf['BROKER_FAILOVER_STRATEGY'] = 'check_cluster_config'

    @app.task(name='cluster-update')
    def cluster_update(nodes):
        cluster.set_cluster_nodes(nodes)
        factory = DaemonFactory()
        daemon = factory.load(daemon_name)
        daemon.cluster = nodes
        factory.save(daemon)
