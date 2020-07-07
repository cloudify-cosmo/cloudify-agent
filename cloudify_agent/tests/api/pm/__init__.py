#########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
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

from functools import wraps
from mock import _get_target
from mock import patch
import pytest

from cloudify import amqp_client, constants
from cloudify.utils import LocalCommandRunner
from cloudify.error_handling import deserialize_known_exception

from cloudify_agent.api import utils
from cloudify_agent.api import exceptions
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.api.plugins import installer

from cloudify_agent.tests import BaseTest
from cloudify_agent.tests import resources
from cloudify_agent.tests import utils as test_utils


BUILT_IN_TASKS = [
    'cloudify.dispatch.dispatch',
    'cluster-update'
]
PLUGIN_NAME = 'plugin'
DEPLOYMENT_ID = 'deployment'


class BaseDaemonLiveTestCase(BaseTest):

    def setUp(self):
        super(BaseDaemonLiveTestCase, self).setUp()
        self.runner = LocalCommandRunner(logger=self.logger)
        self.daemons = []

    def tearDown(self):
        super(BaseDaemonLiveTestCase, self).tearDown()
        if os.name == 'nt':
            # with windows we need to stop and remove the service
            nssm_path = utils.get_absolute_resource_path(
                os.path.join('pm', 'nssm', 'nssm.exe'))
            for daemon in self.daemons:
                self.runner.run('sc stop {0}'.format(daemon.name),
                                exit_on_failure=False)
                self.runner.run('{0} remove {1} confirm'
                                .format(nssm_path, daemon.name),
                                exit_on_failure=False)
        else:
            self.runner.run("pkill -9 -f 'cloudify_agent.worker'",
                            exit_on_failure=False)

    def get_agent_dict(self, env, name='host'):
        node_instances = env.storage.get_node_instances()
        agent_host = [n for n in node_instances if n['name'] == name][0]
        return agent_host['runtime_properties']['cloudify_agent']


def patch_get_source(fn):
    return patch('cloudify_agent.api.plugins.installer.get_plugin_source',
                 lambda plugin, blueprint_id: plugin.get('source'))(fn)


class BaseDaemonProcessManagementTest(BaseDaemonLiveTestCase):
    def tearDown(self):
        super(BaseDaemonProcessManagementTest, self).tearDown()
        installer.uninstall_source(plugin=self.plugin_struct())
        installer.uninstall_source(plugin=self.plugin_struct(),
                                   deployment_id=DEPLOYMENT_ID)

    @property
    def daemon_cls(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def create_daemon(self, **attributes):
        name = utils.internal.generate_agent_name()

        params = {
            'rest_host': ['127.0.0.1'],
            'broker_ip': ['127.0.0.1'],
            'user': self.username,
            'workdir': self.temp_folder,
            'logger': self.logger,
            'name': name,
            'queue': '{0}-queue'.format(name),
            'local_rest_cert_file': self._rest_cert_path,
            'broker_ssl_enabled': False,  # No SSL on the CI machines
        }
        params.update(attributes)

        factory = DaemonFactory()
        daemon = self.daemon_cls(**params)
        factory.save(daemon)
        self.addCleanup(factory.delete, daemon.name)
        self.daemons.append(daemon)
        return daemon

    def test_create(self):
        daemon = self.create_daemon()
        daemon.create()

    def test_create_overwrite(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        self.wait_for_daemon_alive(daemon.queue)

        daemon.create()
        daemon.configure()
        daemon.start()

        self.wait_for_daemon_alive(daemon.queue)
        daemon.stop()
        self.wait_for_daemon_dead(daemon.queue)

    def test_configure(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def test_start(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()

    def test_start_delete_amqp_queue(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()

        # this creates the queue
        daemon.start()

        daemon.stop()
        daemon.start(delete_amqp_queue=True)

    @patch_get_source
    def test_start_with_error(self):
        if os.name == 'nt':
            log_dir = 'H:\\WATT_NONEXISTENT_DIR\\lo'
        else:
            log_dir = '/root/no_permission'
        daemon = self.create_daemon(log_dir=log_dir)
        daemon.create()
        daemon.configure()
        if os.name == 'nt':
            expected_error = '.*WATT_NONEXISTENT_DIR.*'
        else:
            expected_error = ".*Permission denied: /root/no_permission.*"
        with pytest.raises(exceptions.DaemonError, match=expected_error):
            daemon.start(timeout=5)

    def test_start_short_timeout(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        with pytest.raises(exceptions.DaemonStartupTimeout,
                           match='.*failed to start in -1 seconds.*'):
            daemon.start(timeout=-1)

    def test_status(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        assert not daemon.status()
        daemon.start()
        assert daemon.status()

    def test_stop(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.stop()
        self.wait_for_daemon_dead(daemon.queue)

    def test_stop_short_timeout(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        with pytest.raises(exceptions.DaemonShutdownTimeout,
                           match='.*failed to stop in -1 seconds.*'):
            daemon.stop(timeout=-1)

    @patch_get_source
    def test_restart(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        installer.install(self.plugin_struct())
        daemon.start()
        daemon.restart()

    def test_two_daemons(self):
        daemon1 = self.create_daemon()
        daemon1.create()
        daemon1.configure()

        daemon1.start()
        self.assert_daemon_alive(daemon1.queue)

        daemon2 = self.create_daemon()
        daemon2.create()
        daemon2.configure()

        daemon2.start()
        self.assert_daemon_alive(daemon2.queue)

    @patch_get_source
    def test_conf_env_variables(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        installer.install(self.plugin_struct())
        daemon.start()

        expected = {
            constants.REST_HOST_KEY: ','.join(daemon.rest_host),
            constants.REST_PORT_KEY: str(daemon.rest_port),
            constants.MANAGER_FILE_SERVER_URL_KEY: ','.join(
                'https://{0}:{1}/resources'.format(host, daemon.rest_port)
                for host in daemon.rest_host),
            constants.AGENT_WORK_DIR_KEY: daemon.workdir,
        }

        def _get_env_var(var):
            return self.send_task(
                task_name='mock_plugin.tasks.get_env_variable',
                queue=daemon.queue,
                kwargs={'env_variable': var})

        def _check_env_var(var, expected_value):
            _value = _get_env_var(var)
            assert _value == expected_value

        for key, value in expected.items():
            _check_env_var(key, value)

    @patch_get_source
    def test_extra_env(self):
        daemon = self.create_daemon()
        daemon.extra_env_path = utils.env_to_file(
            {'TEST_ENV_KEY': 'TEST_ENV_VALUE'},
            posix=os.name == 'posix'
        )
        daemon.create()
        daemon.configure()
        installer.install(self.plugin_struct())
        daemon.start()

        # check the env file was properly sourced by querying the env
        # variable from the daemon process. this is done by a task
        value = self.send_task(
            task_name='mock_plugin.tasks.get_env_variable',
            queue=daemon.queue,
            kwargs={'env_variable': 'TEST_ENV_KEY'})
        assert value == 'TEST_ENV_VALUE'

    @patch_get_source
    def test_execution_env(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        installer.install(self.plugin_struct())
        daemon.start()

        # check that cloudify.dispatch.dispatch 'execution_env' processing
        # works.
        # not the most ideal place for this test. but on the other hand
        # all the boilerplate is already here, so this is too tempting.
        value = self.send_task(
            task_name='mock_plugin.tasks.get_env_variable',
            queue=daemon.queue,
            kwargs={'env_variable': 'TEST_ENV_KEY2'},
            execution_env={'TEST_ENV_KEY2': 'TEST_ENV_VALUE2'})
        assert value == 'TEST_ENV_VALUE2'

    def test_delete(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def test_delete_before_stop(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        pytest.raises(exceptions.DaemonStillRunningException,
                      daemon.delete)

    def test_delete_before_stop_with_force(self):
        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        daemon.start()
        daemon.delete(force=True)
        self.wait_for_daemon_dead(daemon.queue)

    @patch_get_source
    def test_logging(self):
        message = 'THIS IS THE TEST MESSAGE LOG CONTENT'

        daemon = self.create_daemon()
        daemon.create()
        daemon.configure()
        installer.install(self.plugin_struct())
        installer.install(self.plugin_struct(),
                          deployment_id=DEPLOYMENT_ID)
        daemon.start()

        def log_and_assert(_message, _deployment_id=None):
            self.send_task(
                task_name='mock_plugin.tasks.do_logging',
                queue=daemon.queue,
                kwargs={'message': _message},
                deployment_id=_deployment_id)

            name = _deployment_id if _deployment_id else '__system__'
            logdir = os.path.join(daemon.workdir, 'logs')
            logfile = os.path.join(logdir, '{0}.log'.format(name))
            try:
                with open(logfile) as f:
                    assert _message in f.read()
            except IOError:
                self.logger.warning('{0} content: {1}'
                                    .format(logdir, os.listdir(logdir)))
                raise

        # Test __system__ logs
        log_and_assert(message)
        # Test deployment logs
        log_and_assert(message, DEPLOYMENT_ID)

    @staticmethod
    def plugin_struct(plugin_name='mock-plugin'):
        return {
            'source': os.path.join(resources.get_resource('plugins'),
                                   plugin_name),
            'name': PLUGIN_NAME
        }

    def send_task(self,
                  task_name,
                  queue,
                  deployment_id=None,
                  args=None,
                  kwargs=None,
                  timeout=10,
                  execution_env=None):
        cloudify_context = test_utils.op_context(task_name,
                                                 task_target=queue,
                                                 plugin_name=PLUGIN_NAME,
                                                 execution_env=execution_env,
                                                 deployment_id=deployment_id)
        kwargs = kwargs or {}
        kwargs['__cloudify_context'] = cloudify_context
        handler = amqp_client.BlockingRequestResponseHandler(queue)
        client = amqp_client.get_client()
        client.add_handler(handler)
        with client:
            task = {'cloudify_task': {'kwargs': kwargs}}
            result = handler.publish(task, routing_key='operation',
                                     timeout=timeout)
        error = result.get('error')
        if error:
            raise deserialize_known_exception(error)
        else:
            return result.get('result')
