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
from celery import Celery

from cloudify import constants

from cloudify.utils import get_daemon_name
from cloudify.utils import get_daemon_storage_dir


broker_url = os.environ.get(constants.CELERY_BROKER_URL_KEY, 'amqp://')

try:
    # running inside an agent
    daemon_name = get_daemon_name()
except KeyError:
    # running outside an agent
    daemon_name = None

# This attribute is used as the celery App instance.
# it is referenced in two ways:
#   1. Celery command line --app options.
#   2. The operation decorator uses app.task as the underlying
#      celery task decorator. (cloudify.decorators)
app = Celery(broker=broker_url)

# result backend should be configured like this
# instead of in the constructor because of an issue with celery
# result backends running on windows hosts
# see https://github.com/celery/celery/issues/897
app.conf.update(
    CELERY_RESULT_BACKEND=broker_url
)


if daemon_name:

    # Setting a new exception hook to catch any exceptions
    # on celery startup and write them to a file. This file
    # is later read for querying if celery has started successfully.
    current_excepthook = sys.excepthook

    def new_excepthook(exception_type, value, the_traceback):

        # use the storage directory because the work directory might have
        # been created under a different user, in which case we don't have
        # permissions to write to it.
        storage = get_daemon_storage_dir()
        if not os.path.exists(storage):
            os.makedirs(storage)
        error_dump_path = os.path.join(
            get_daemon_storage_dir(),
            '{0}.err'.format(daemon_name))
        with open(error_dump_path, 'w') as f:
            f.write('Type: {0}\n'.format(exception_type))
            f.write('Value: {0}\n'.format(value))
            traceback.print_tb(the_traceback, file=f)
        current_excepthook(exception_type, value, the_traceback)

    sys.excepthook = new_excepthook
