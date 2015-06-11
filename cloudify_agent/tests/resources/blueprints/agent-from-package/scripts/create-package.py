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
from cloudify_agent.tests.resources import get_resource
from cloudify.utils import LocalCommandRunner
from cloudify.exceptions import NonRecoverableError


config = {
    'cloudify_agent_module': ctx.node.properties['cloudify_agent_module'],
    'requirements_file': ctx.node.properties.get('requirements_file')
}

resource_base = ctx.node.properties['resource_base']
file_server_port = ctx.node.properties['file_server_port']


# This should be integrated into packager
# For now, this is the best place
def create_windows_installer():
    runner = LocalCommandRunner()
    wheelhouse = get_resource('winpackage/source/wheels')

    pip_cmd = 'pip wheel --wheel-dir {wheel_dir} --requirement {req_file}'.\
        format(wheel_dir=wheelhouse, req_file=config['requirements_file'])

    ctx.logger.info('Building wheels into: {0}'.format(wheelhouse))
    runner.run(pip_cmd)

    pip_cmd = 'pip wheel --find-links {wheel_dir} --wheel-dir {wheel_dir} ' \
              '{repo_url}'.format(wheel_dir=wheelhouse,
                                  repo_url=config['cloudify_agent_module'])
    runner.run(pip_cmd)

    iscc_cmd = 'iscc {0}'.format(get_resource(os.path.join('winpackage',
                                                           'create.iss')))
    os.environ['VERSION'] = '0'
    os.environ['iscc_output'] = os.getcwd()
    runner.run(iscc_cmd)

ctx.logger.info('Changing directory into {0}'.format(resource_base))
original = os.getcwd()
try:
    ctx.logger.info('Creating Agent Package')
    os.chdir(resource_base)
    if platform.system() == 'Linux':
        packager.create(config=config,
                        config_file=None,
                        force=False,
                        verbose=False)
        distname, _, distid = platform.dist()
        package_url = 'http://localhost:{0}/{1}-{2}-agent.tar.gz' \
            .format(file_server_port, distname, distid)
    elif platform.system() == 'Windows':
        create_windows_installer()
        package_url = 'http://localhost:{0}/cloudify_agent_0.exe' \
            .format(file_server_port)
    else:
        raise NonRecoverableError('Platform not supported: {0}'
                                  .format(platform.system()))
finally:
    os.chdir(original)

ctx.logger.info('Package created successfully: {0}'.format(package_url))
ctx.logger.info('Setting runtime properties')
ctx.instance.runtime_properties['package_url'] = package_url
