#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

import os
import getpass
import logging
import testtools
import tempfile
import shutil
from functools import wraps

from mock import _get_target
from mock import patch

from celery import Celery
from cloudify.utils import LocalCommandRunner
from cloudify.utils import setup_logger


BUILT_IN_TASKS = [
    'script_runner.tasks.execute_workflow',
    'script_runner.tasks.run',
    'diamond_agent.tasks.install',
    'diamond_agent.tasks.uninstall',
    'diamond_agent.tasks.start',
    'diamond_agent.tasks.stop',
    'diamond_agent.tasks.add_collectors',
    'diamond_agent.tasks.del_collectors',
    'worker_installer.tasks.install',
    'worker_installer.tasks.uninstall',
    'worker_installer.tasks.start',
    'worker_installer.tasks.stop',
    'worker_installer.tasks.restart',
    'plugin_installer.tasks.install',
    'windows_agent_installer.tasks.install',
    'windows_agent_installer.tasks.uninstall',
    'windows_agent_installer.tasks.start',
    'windows_agent_installer.tasks.stop',
    'windows_agent_installer.tasks.restart',
    'windows_plugin_installer.tasks.install'
]

CLOUDIFY_STORAGE_FOLDER = '/tmp/.cloudify-agent/agents'


def travis():
    return 'TRAVIS_BUILD_DIR' in os.environ


def patch_unless_travis(target, new):

    if not travis():
        return patch(target, new)
    else:
        getter, attribute = _get_target(target)
        return patch(target, getattr(getter(), attribute))


def only_travis(func):

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not travis():
            raise RuntimeError('Error! This test cannot be executed '
                               'outside of the travis CI '
                               'system since it may corrupt '
                               'your local system files')
        func(*args, **kwargs)

    return wrapper


class BaseDaemonLiveTestCase(testtools.TestCase):

    def setUp(self):
        super(BaseDaemonLiveTestCase, self).setUp()
        self.celery = Celery(broker='amqp://',
                             backend='amqp://')
        self.logger = setup_logger(
            'cloudify-agent.tests.api.pm',
            logger_level=logging.DEBUG)
        self.runner = LocalCommandRunner(self.logger)
        self.temp_folder = tempfile.mkdtemp(prefix='cloudify-agent-tests-')
        self.currdir = os.getcwd()
        self.username = getpass.getuser()
        self.logger.info('Working directory: {0}'.format(self.temp_folder))
        os.chdir(self.temp_folder)

    def tearDown(self):
        super(BaseDaemonLiveTestCase, self).tearDown()
        os.chdir(self.currdir)
        pong = self.celery.control.ping()
        if pong:
            self.runner.run("pkill -9 -f 'celery'")

    def _smakedirs(self, dirs):
        if not os.path.exists(dirs):
            os.makedirs(dirs)

    def _srmtree(self, tree):
        if os.path.exists(tree):
            shutil.rmtree(tree)

    def assert_registered_tasks(self, queue, additional_tasks=None):
        if not additional_tasks:
            additional_tasks = set()
        destination = 'celery@{0}'.format(queue)
        inspect = self.celery.control.inspect(destination=[destination])
        registered = inspect.registered() or {}

        def include(task):
            return 'celery' not in task

        daemon_tasks = set(filter(include, set(registered[destination])))
        expected_tasks = set(BUILT_IN_TASKS)
        expected_tasks.update(additional_tasks)
        self.assertEqual(expected_tasks, daemon_tasks)

    def assert_daemon_alive(self, queue):
        destination = 'celery@{0}'.format(queue)
        inspect = self.celery.control.inspect(destination=[destination])
        stats = (inspect.stats() or {}).get(destination)
        self.assertTrue(stats is not None)

    def assert_daemon_dead(self, queue):
        destination = 'celery@{0}'.format(queue)
        inspect = self.celery.control.inspect(destination=[destination])
        stats = (inspect.stats() or {}).get(destination)
        self.assertTrue(stats is None)
