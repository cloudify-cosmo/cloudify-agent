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

import os
import platform

from agent_packager import packager
from cloudify import ctx

config = {
    'cloudify_agent_module': ctx.node.properties['cloudify_agent_module'],
    'requirements_file': ctx.node.properties.get('requirements_file')
}

resource_base = ctx.node.properties['resource_base']
ctx.logger.info('Changing directory into {0}'.format(resource_base))
original = os.getcwd()
try:
    ctx.logger.info('Creating Agent Package')
    os.chdir(resource_base)
    packager.create(config=config,
                    config_file=None,
                    force=False,
                    verbose=False)
finally:
    os.chdir(original)

dist = platform.dist()

ctx.logger.info('Constructing package_url...'.format(resource_base))
package_url = 'http://localhost:53229/{0}-{1}-agent.tar.gz'\
    .format(dist[0], dist[2])
ctx.logger.info('Package created successfully: {0}'.format(package_url))
ctx.logger.info('Setting runtime properties')
ctx.instance.runtime_properties['package_url'] = package_url
