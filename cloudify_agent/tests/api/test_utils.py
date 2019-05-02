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
import tempfile
import unittest

from cloudify.utils import setup_logger

import cloudify_agent
from cloudify_agent.api import utils
from cloudify_agent.api import defaults
from cloudify_agent.api.pm.base import Daemon

from cloudify_agent.tests import BaseTest
from cloudify_agent.tests import utils as test_utils


class TestUtils(BaseTest, unittest.TestCase):

    def setUp(self):
        super(TestUtils, self).setUp()
        self.fs = None

    @classmethod
    def setUpClass(cls):
        cls.logger = setup_logger('cloudify_agent.tests.api.test_utils')
        cls.file_server_resource_base = tempfile.mkdtemp(
            prefix='file-server-resource-base')
        cls.fs = test_utils.FileServer(root_path=cls.file_server_resource_base)
        cls.fs.start()
        cls.file_server_url = 'http://localhost:{0}'.format(cls.fs.port)

    @classmethod
    def tearDownClass(cls):
        cls.fs.stop()

    def test_daemon_to_dict(self):
        daemon = Daemon(rest_host='127.0.0.1', name='name',
                        queue='queue', broker_ip='127.0.0.1',
                        local_rest_cert_file=self._rest_cert_path)
        daemon_json = utils.internal.daemon_to_dict(daemon)
        self.assertEqual(daemon_json['rest_host'], '127.0.0.1')
        self.assertEqual(daemon_json['broker_ip'], ['127.0.0.1'])
        self.assertEqual(daemon_json['name'], 'name')
        self.assertEqual(daemon_json['queue'], 'queue')

    def test_get_resource(self):
        resource = utils.get_resource(os.path.join(
            'pm',
            'initd',
            'initd.conf.template'
        ))
        self.assertIsNotNone(resource)

    def test_rendered_template_to_file(self):
        temp = utils.render_template_to_file(
            template_path=os.path.join('pm', 'initd', 'initd.conf.template'),
            rest_host='127.0.0.1'
        )
        with open(temp) as f:
            rendered = f.read()
            self.assertTrue('export REST_HOST="127.0.0.1"' in rendered)

    def test_resource_to_tempfile(self):
        temp = utils.resource_to_tempfile(
            resource_path=os.path.join('pm', 'initd', 'initd.conf.template')
        )
        self.assertTrue(os.path.exists(temp))

    def test_content_to_tempfile(self):
        temp = utils.content_to_file(
            content='content'
        )
        with open(temp) as f:
            self.assertEqual('content{0}'
                             .format(os.linesep),
                             f.read())

    def test_generate_agent_name(self):
        name = utils.internal.generate_agent_name()
        self.assertIn(defaults.CLOUDIFY_AGENT_PREFIX, name)

    def test_get_broker_url(self):
        config = dict(broker_ip='10.50.50.3',
                      broker_user='us#er',
                      broker_pass='pa$$word',
                      broker_vhost='vh0$t',
                      broker_ssl_enabled=True)
        self.assertEqual('amqp://us%23er:pa%24%24word@10.50.50.3:5671/vh0$t',
                         utils.internal.get_broker_url(config))
