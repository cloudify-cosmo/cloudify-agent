########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
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
import uuid
import time

from cloudify_agent.installer import script
from system_tests import resources
from cloudify.state import current_ctx
from cloudify.mocks import MockCloudifyContext
from cloudify.utils import setup_logger
from cloudify.compute import create_multi_mimetype_userdata
from cosmo_tester.framework import testenv


class AgentInstallerTest(testenv.TestCase):

    expected_file_content = 'CONTENT'

    @classmethod
    def setUpClass(cls):
        cls.logger = setup_logger(
            'cloudify_agent.system_tests.manager.test_agent_installer')

    def test_3_2_agent(self):

        self.blueprint_yaml = resources.get_resource(
            '3-2-agent-blueprint/3-2-agent-mispelled-blprint.yaml')
        self.upload_deploy_and_execute_install(
            inputs={
                'image': self.env.ubuntu_trusty_image_id,
                'flavor': self.env.small_flavor_id
            }
        )
        self.execute_uninstall()

    def test_ssh_agent(self):

        self.blueprint_yaml = resources.get_resource(
            'ssh-agent-blueprint/ssh-agent-blueprint.yaml')
        self.upload_deploy_and_execute_install(
            inputs={
                'image': self.env.ubuntu_trusty_image_id,
                'flavor': self.env.small_flavor_id
            }
        )
        self.execute_uninstall()

    def _test_agent_alive_after_reboot(self, blueprint, inputs):

        self.blueprint_yaml = resources.get_resource(blueprint)
        value = str(uuid.uuid4())
        inputs['value'] = value
        deployment_id = self.test_id
        self.upload_deploy_and_execute_install(
            deployment_id=deployment_id,
            inputs=inputs)
        self.cfy.execute_workflow(
            workflow='execute_operation',
            deployment_id=deployment_id,
            parameters={
                'operation': 'cloudify.interfaces.reboot_test.reboot',
                'node_ids': ['host']
            },
            include_logs=True)
        self.execute_uninstall(deployment_id=deployment_id)
        app = self.client.node_instances.list(node_id='application',
                                              deployment_id=deployment_id)[0]
        self.assertEquals(value, app.runtime_properties['value'])

    def test_ubuntu_agent_alive_after_reboot(self):

        self._test_agent_alive_after_reboot(
            blueprint='reboot-vm-blueprint/reboot-unix-vm-blueprint.yaml',
            inputs={
                'image': self.env.ubuntu_trusty_image_id,
                'flavor': self.env.small_flavor_id,
                'user': 'ubuntu'
            })

    def test_centos_agent_alive_after_reboot(self):

        self._test_agent_alive_after_reboot(
            blueprint='reboot-vm-blueprint/reboot-unix-vm-blueprint.yaml',
            inputs={
                'image': self.env.centos_7_image_name,
                'flavor': self.env.small_flavor_id,
                'user': self.env.centos_7_image_user
            })

    def test_winrm_agent_alive_after_reboot(self):

        self._test_agent_alive_after_reboot(
            blueprint='reboot-vm-blueprint/reboot-winrm-vm-blueprint.yaml',
            inputs={
                'image': self.env.windows_image_name,
                'flavor': self.env.small_flavor_id
            })

    def test_winrm_agent(self):

        self.blueprint_yaml = resources.get_resource(
            'winrm-agent-blueprint/winrm-agent-blueprint.yaml')
        self.upload_deploy_and_execute_install(
            inputs={
                'image': self.env.windows_image_name,
                'flavor': self.env.medium_flavor_id
            }
        )
        self.execute_uninstall()

    # Two different tests for ubuntu/centos
    # because of different disable requiretty logic
    def test_centos_core_userdata_agent(self):
        self._test_linux_userdata_agent(image=self.env.centos_7_image_name,
                                        flavor=self.env.small_flavor_id,
                                        user=self.env.centos_7_image_user,
                                        install_method='init_script')

    def test_ubuntu_trusty_userdata_agent(self):
        self._test_linux_userdata_agent(image=self.env.ubuntu_trusty_image_id,
                                        flavor=self.env.small_flavor_id,
                                        user='ubuntu',
                                        install_method='init_script')

    def test_ubuntu_trusty_provided_userdata_agent(self):
        name = 'cloudify_agent'
        user = 'ubuntu'
        install_userdata = install_script(name=name,
                                          windows=False,
                                          user=user,
                                          manager_ip=self._manager_ip())
        self._test_linux_userdata_agent(image=self.env.ubuntu_trusty_image_id,
                                        flavor=self.env.small_flavor_id,
                                        user=user,
                                        install_method='provided',
                                        name=name,
                                        install_userdata=install_userdata)

    def _test_linux_userdata_agent(self, image, flavor, user, install_method,
                                   install_userdata=None, name=None):
        file_path = '/tmp/test_file'
        userdata = '#! /bin/bash\necho {0} > {1}\nchmod 777 {1}'.format(
            self.expected_file_content, file_path)
        if install_userdata:
            userdata = create_multi_mimetype_userdata([userdata,
                                                       install_userdata])
        self._test_userdata_agent(image=image,
                                  flavor=flavor,
                                  user=user,
                                  os_family='linux',
                                  userdata=userdata,
                                  file_path=file_path,
                                  install_method=install_method,
                                  name=name)

    def test_windows_userdata_agent(self,
                                    install_method='init_script',
                                    name=None,
                                    install_userdata=None):
        user = 'Administrator'
        file_path = 'C:\\Users\\{0}\\test_file'.format(user)
        userdata = '#ps1_sysnative \nSet-Content {1} "{0}"'.format(
            self.expected_file_content, file_path)
        if install_userdata:
            userdata = create_multi_mimetype_userdata([userdata,
                                                       install_userdata])
        self._test_userdata_agent(image=self.env.windows_image_name,
                                  flavor=self.env.medium_flavor_id,
                                  user=user,
                                  os_family='windows',
                                  userdata=userdata,
                                  file_path=file_path,
                                  install_method=install_method,
                                  name=name)

    def test_windows_provided_userdata_agent(self):
        name = 'cloudify_agent'
        install_userdata = install_script(name=name,
                                          windows=True,
                                          user='Administrator',
                                          manager_ip=self._manager_ip())
        self.test_windows_userdata_agent(install_method='provided',
                                         name=name,
                                         install_userdata=install_userdata)

    def _test_userdata_agent(self, image, flavor, user, os_family,
                             userdata, file_path, install_method,
                             name=None):
        deployment_id = 'userdata{0}'.format(time.time())
        self.blueprint_yaml = resources.get_resource(
            'userdata-agent-blueprint/userdata-agent-blueprint.yaml')
        self.upload_deploy_and_execute_install(
            deployment_id=deployment_id,
            inputs={
                'image': image,
                'flavor': flavor,
                'agent_user': user,
                'os_family': os_family,
                'userdata': userdata,
                'file_path': file_path,
                'install_method': install_method,
                'name': name
            }
        )
        self.assert_outputs({'MY_ENV_VAR': 'MY_ENV_VAR_VALUE',
                             'file_content': self.expected_file_content},
                            deployment_id=deployment_id)
        self.execute_uninstall(deployment_id=deployment_id)

    def _manager_ip(self):
        nova_client, _, _ = self.env.handler.openstack_clients()
        for server in nova_client.servers.list():
            if server.name == self.env.management_server_name:
                for network, network_ips in server.networks.items():
                    if network == self.env.management_network_name:
                        return network_ips[0]
        self.fail('Failed finding manager ip')


def install_script(name, windows, user, manager_ip):
    ctx = MockCloudifyContext(
        node_id='node',
        properties={'agent_config': {
            'user': user,
            'windows': windows,
            'install_method': 'provided',
            'manager_ip': manager_ip,
            'name': name
        }})
    try:
        current_ctx.set(ctx)
        os.environ['MANAGER_FILE_SERVER_URL'] = 'http://{0}:53229'.format(
            manager_ip)
        init_script = script.init_script(cloudify_agent={})
    finally:
        os.environ.pop('MANAGER_FILE_SERVER_URL')
        current_ctx.clear()
    result = '\n'.join(init_script.split('\n')[:-1])
    if windows:
        return '{0}\n' \
               'DownloadAndExtractAgentPackage\n' \
               'ExportDaemonEnv\n' \
               'ConfigureAgent'.format(result)
    else:
        return '{0}\n' \
               'install_agent'.format(result)
