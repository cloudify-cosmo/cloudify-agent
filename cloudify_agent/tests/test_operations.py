#########
# Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
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

import tempfile
import uuid

from celery import Celery

from cloudify.exceptions import NonRecoverableError
from cloudify import constants
from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner

from cloudify_agent import operations
from cloudify_agent import VIRTUALENV

from cloudify_agent.tests import utils
from cloudify_agent.api.utils import get_pip_path
from cloudify_agent.tests import file_server
from cloudify_agent.tests.api.pm import BaseDaemonLiveTestCase
from cloudify_agent.tests.api.pm import only_ci
from cloudify_agent.tests import BaseTest


class CloudifyAgentLiveTasksTest(BaseDaemonLiveTestCase):

    fs = None

    @classmethod
    def setUpClass(cls):

        cls.logger = setup_logger('cloudify_agent.tests.test_tasks')
        cls.runner = LocalCommandRunner(cls.logger)

        cls.file_server_resource_base = tempfile.mkdtemp(
            prefix='file-server-resource-base')
        cls.fs = file_server.FileServer(
            root_path=cls.file_server_resource_base)
        cls.fs.start()
        cls.file_server_url = 'http://localhost:{0}'.format(cls.fs.port)

        utils.create_plugin_tar(
            plugin_dir_name='mock-plugin',
            target_directory=cls.file_server_resource_base)

        cls.celery = Celery(broker='amqp://',
                            backend='amqp://')

    @classmethod
    def tearDownClass(cls):
        cls.fs.stop()

    def _assert_plugin_installed(self, plugin_name):
        out = self.runner.run('{0} list'.format(get_pip_path())).output
        self.assertIn(plugin_name, out)

    def _create_plugin_url(self, plugin_tar_name):
        return '{0}/{1}'.format(self.file_server_url, plugin_tar_name)

    def _uninstall_package_if_exists(self, plugin_name):
        out = self.runner.run('{0} list'.format(get_pip_path())).output
        if plugin_name in out:
            self.runner.run('{0} uninstall -y {1}'.format(
                get_pip_path(), plugin_name), stdout_pipe=False)

    @only_ci
    def test_install_plugins_and_restart(self):
        name = 'cloudify-agent-{0}'.format(uuid.uuid4())
        queue = '{0}-queue'.format(name)

        self.runner.run('{0}/bin/cfy-agent --debug daemons create '
                        '--manager-ip=127.0.0.1 --name={1} '
                        '--process-management=init.d '
                        '--queue={2}'
                        .format(VIRTUALENV, name, queue),
                        stdout_pipe=False)
        self.runner.run('{0}/bin/cfy-agent --debug daemons '
                        'configure --name={1}'
                        .format(VIRTUALENV, name),
                        stdout_pipe=False)
        self.runner.run('{0}/bin/cfy-agent --debug daemons '
                        'start --name={1}'
                        .format(VIRTUALENV, name),
                        stdout_pipe=False)

        new_name = 'cloudify-agent-{0}'.format(uuid.uuid4())

        try:
            # now lets send the install_plugins task
            # this simulates what they cloudify manager will do
            self.logger.info('Installing mock-plugin on the current agent')
            self.celery.send_task(
                name='cloudify_agent.operations.install_plugins',
                queue=queue,
                args=[[{'source': '{0}/mock-plugin.tar'
                       .format(self.file_server_url),
                        'name': 'mock-plugin'}]],
                ).get(timeout=30)
            self._assert_plugin_installed('mock-plugin')

            # now lets send the restart task
            # this simulates what they cloudify manager will do
            self.logger.info('Attempting to restart the agent')
            self.celery.send_task(
                name='cloudify_agent.operations.restart',
                queue=queue,
                args=[new_name],
                ).get()

            # lets wait for the new daemon to start
            self.wait_for_daemon_alive(new_name)

            # lets see that the old daemon is dead
            self.wait_for_daemon_dead(name=name)

            # lets make sure the new agent recognizes the installed plugin
            self.celery.send_task(
                name='mock_plugin.tasks.run',
                queue=queue
            ).get(timeout=5)

        finally:
            self._uninstall_package_if_exists('mock-plugin')

    @only_ci
    def test_stop(self):

        name = 'cloudify-agent-{0}'.format(uuid.uuid4())
        queue = '{0}-queue'.format(name)

        self.runner.run('{0}/bin/cfy-agent --debug daemons create '
                        '--manager-ip=127.0.0.1 --name={1} '
                        '--process-management=init.d '
                        '--queue={2}'
                        .format(VIRTUALENV, name, queue),
                        stdout_pipe=False)
        self.runner.run('{0}/bin/cfy-agent --debug daemons '
                        'configure --name={1}'
                        .format(VIRTUALENV, name),
                        stdout_pipe=False)
        self.runner.run('{0}/bin/cfy-agent --debug daemons '
                        'start --name={1}'
                        .format(VIRTUALENV, name),
                        stdout_pipe=False)

        # now lets send the stop task
        # this simulates what they cloudify manager will do
        self.celery.send_task(
            name='cloudify_agent.operations.stop',
            queue=queue
            ).get(timeout=30)

        # lets see that the old daemon is dead
        self.wait_for_daemon_dead(name=name)


class CloudifyAgentTasksUnitTest(BaseTest):

    def test_get_url_and_args_http_no_args(self):
        plugin = {'source': 'http://google.com'}
        url = operations.get_plugin_source(plugin)
        args = operations.get_plugin_args(plugin)
        self.assertEqual(url, 'http://google.com')
        self.assertEqual(args, '')

    def test_get_url_https(self):
        plugin = {
            'source': 'https://google.com',
            'install_arguments': '--pre'
        }
        url = operations.get_plugin_source(plugin)
        args = operations.get_plugin_args(plugin)

        self.assertEqual(url, 'https://google.com')
        self.assertEqual(args, '--pre')

    def test_get_url_faulty_schema(self):
        self.assertRaises(NonRecoverableError,
                          operations.get_plugin_source,
                          {'source': 'bla://google.com'})

    def test_get_plugin_source_from_blueprints_dir(self):
        plugin = {
            'source': 'plugin-dir-name'
        }
        with utils.env(constants.MANAGER_FILE_SERVER_BLUEPRINTS_ROOT_URL_KEY,
                       'localhost'):
            source = operations.get_plugin_source(
                plugin,
                blueprint_id='blueprint_id')
        self.assertEqual(
            'localhost/blueprint_id/plugins/plugin-dir-name.zip',
            source)
