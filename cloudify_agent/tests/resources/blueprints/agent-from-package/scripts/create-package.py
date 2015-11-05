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

from cloudify import ctx
from cloudify_agent.tests.utils import create_agent_package

config = {
    'cloudify_agent_module': ctx.node.properties['cloudify_agent_module'],
    'requirements_file': ctx.node.properties.get('requirements_file')
}

resource_base = ctx.node.properties['resource_base']
file_server_port = ctx.node.properties['file_server_port']

package_name = create_agent_package(resource_base, config, ctx.logger)
package_url = 'http://localhost:{0}/{1}'.format(file_server_port, package_name)


ctx.logger.info('Package created successfully: {0}'.format(package_url))
ctx.logger.info('Setting runtime properties')
ctx.instance.runtime_properties['package_url'] = package_url
