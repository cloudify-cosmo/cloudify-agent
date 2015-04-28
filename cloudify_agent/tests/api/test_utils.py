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

import testtools
import os

import cloudify_agent
from cloudify_agent.api import utils


class TestUtils(testtools.TestCase):

    def test_get_resource(self):
        resource = utils.get_resource('initd/celeryd.conf.template')
        path_to_resource = os.path.join(
            os.path.dirname(cloudify_agent.__file__),
            'resources',
            'initd',
            'celeryd.conf.template'
        )
        with open(path_to_resource) as f:
            self.assertEqual(f.read(), resource)

    def test_rendered_template_to_file(self):
        tempfile = utils.render_template_to_file(
            template_path='initd/celeryd.conf.template',
            manager_ip='127.0.0.1'
        )
        with open(tempfile) as f:
            rendered = f.read()
            self.assertTrue('export MANAGER_IP=127.0.0.1' in rendered)

    def test_resource_to_tempfile(self):
        tempfile = utils.resource_to_tempfile(
            resource_path='initd/celeryd.conf.template'
        )
        path_to_resource = os.path.join(
            os.path.dirname(cloudify_agent.__file__),
            'resources',
            'initd',
            'celeryd.conf.template'
        )
        with open(path_to_resource) as expected:
            with open(tempfile) as actual:
                self.assertEqual('{0}{1}'.format(expected.read(),
                                                 os.linesep),
                                 actual.read())

    def test_content_to_tempfile(self):
        tempfile = utils.content_to_file(
            content='content'
        )
        with open(tempfile) as f:
            self.assertEqual('content{0}'
                             .format(os.linesep),
                             f.read())

    def test_run_script_from_temp_file(self):
        content = '#!/bin/bash\necho success'
        path = utils.content_to_file(content)
        os.system('chmod +x {0}'.format(path))
        code = os.system(path)
        self.assertEqual(0, code)

    def test_env_to_file(self):
        env_path = utils.env_to_file({'key': 'value'})
        with open(env_path) as f:
            content = f.read()
        self.assertTrue('export key=value' in content)
