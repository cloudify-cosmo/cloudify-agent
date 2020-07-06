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

import uuid
import os
import pytest
import shutil

from cloudify_agent.api import exceptions
from cloudify_agent.api import utils
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.tests import get_storage_directory, BaseTest


class TestDaemonFactory(BaseTest):

    def setUp(self):
        super(TestDaemonFactory, self).setUp()
        self.daemon_name = 'test-daemon-{0}'.format(uuid.uuid4())
        self.factory = DaemonFactory(storage=get_storage_directory())
        self.daemon_params = {
            'process_management': 'init.d',
            'name': self.daemon_name,
            'queue': 'queue',
            'rest_host': '127.0.0.1',
            'broker_ip': '127.0.0.1',
            'user': 'user',
            'broker_url': '127.0.0.1',
            'broker_ssl_enabled': True,
            'local_rest_cert_file': self._rest_cert_path
        }

    def test_new_initd(self):
        daemon = self.factory.new(**self.daemon_params)
        assert self.daemon_name == daemon.name
        assert 'queue' == daemon.queue
        assert '127.0.0.1' == daemon.rest_host
        assert 'user' == daemon.user
        assert self._rest_cert_path == daemon.local_rest_cert_file

    def test_new_no_implementation(self):
        pytest.raises(exceptions.DaemonNotImplementedError,
                      self.factory.new,
                      process_management='no-impl')

    def test_save_load_delete(self):

        daemon = self.factory.new(**self.daemon_params)

        self.factory.save(daemon)
        loaded = self.factory.load(self.daemon_name)
        assert 'init.d' == loaded.PROCESS_MANAGEMENT
        assert self.daemon_name == loaded.name
        assert 'queue' == loaded.queue
        assert '127.0.0.1' == loaded.rest_host
        assert 'user' == loaded.user
        self.factory.delete(daemon.name)
        pytest.raises(exceptions.DaemonNotFoundError,
                      self.factory.load, daemon.name)

    def test_load_non_existing(self):
        pytest.raises(exceptions.DaemonNotFoundError,
                      self.factory.load,
                      'non_existing_name')

    def test_load_all(self):

        def _save_daemon(name):
            params = self.daemon_params.copy()
            params['name'] = name
            daemon = self.factory.new(**params)
            self.factory.save(daemon)

        if os.path.exists(get_storage_directory()):
            shutil.rmtree(get_storage_directory())

        daemons = self.factory.load_all()
        assert 0 == len(daemons)
        _save_daemon(utils.internal.generate_agent_name())
        _save_daemon(utils.internal.generate_agent_name())
        _save_daemon(utils.internal.generate_agent_name())

        daemons = self.factory.load_all()
        assert 3 == len(daemons)

    def test_new_existing_agent(self):
        daemon = self.factory.new(**self.daemon_params)

        self.factory.save(daemon)

        # without no_overwrite, this will overwrite the existing daemon
        daemon = self.factory.new(**self.daemon_params)

        pytest.raises(exceptions.DaemonAlreadyExistsError,
                      self.factory.new,
                      no_overwrite=True,
                      **self.daemon_params)
