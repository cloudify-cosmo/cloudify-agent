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
import traceback
import logging
import logging.handlers

from celery import Celery, signals
from celery.utils.log import ColorFormatter
from celery.worker.loops import asynloop

from cloudify.celery import gate_keeper
from cloudify.celery import logging_server

from cloudify_agent.api import utils

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

# This attribute is used as the celery App instance.
# it is referenced in two ways:
#   1. Celery command line --app options.
#   2. cloudify.dispatch.dispatch uses it as the 'task' decorator.
# For app configuration, see cloudify.broker_config.
app = Celery()
gate_keeper.configure_app(app)
logging_server.configure_app(app)

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
