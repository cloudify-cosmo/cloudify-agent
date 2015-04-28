########
# Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
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
import sys
import traceback
from celery import Celery

"""
This module is loaded on celery startup.
"""


broker_url = os.environ.get('CELERY_BROKER_URL', 'amqp://')
work_folder = os.environ.get('CELERYD_WORK_DIR')


# This attribute is used as the celery App instance.
# it is referenced in two ways:
#   1. Celery command line --app options. (celeryd.conf.template)
#   2. The operation decorator uses app.task as the underlying
#      celery task decorator. (cloudify.decorators)
app = Celery(broker=broker_url,
             backend=broker_url)


if work_folder:

    # Setting a new exception hook to catch any exceptions
    # on celery startup and write them to a file. This file
    # is later read for querying if celery has started successfully.
    current_excepthook = sys.excepthook

    def new_excepthook(exception_type, value, the_traceback):
        error_dump_path = os.path.join(work_folder, 'celery_error.out')
        with open(error_dump_path, 'w') as f:
            f.write('Type: {0}\n'.format(exception_type))
            f.write('Value: {0}\n'.format(value))
            traceback.print_tb(the_traceback, file=f)
        current_excepthook(exception_type, value, the_traceback)

    sys.excepthook = new_excepthook
