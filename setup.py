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


from setuptools import setup

install_requires = [
    'click==6.6',
    'wagon==0.3.3',
    'fabric==1.8.3',
    'jinja2==2.7.2',
    'pyzmq==15.1.0',
    'pywinrm==0.0.3',
    'celery==3.1.17',
    'fasteners==0.13.0',
    'virtualenv>=14.0.0,<15.0.0',
    'cloudify-script-plugin==1.4',
    'cloudify-rest-client==3.5a1',
    'cloudify-plugins-common==3.5a1',
]

setup(
    name='cloudify-agent',
    version='3.5a1',
    author='Gigaspaces',
    author_email='cosmo-admin@gigaspaces.com',
    packages=[
        'worker_installer',
        'plugin_installer',
        'windows_agent_installer',
        'windows_plugin_installer',
        'cloudify_agent',
        'cloudify_agent.api',
        'cloudify_agent.shell',
        'cloudify_agent.api.pm',
        'cloudify_agent.installer',
        'cloudify_agent.api.plugins',
        'cloudify_agent.shell.commands'
        'cloudify_agent.installer.config',
        'cloudify_agent.installer.runners',
    ],
    package_data={
        'cloudify_agent': [
            'resources/respawn.sh.template',
            'resources/disable-requiretty.sh',
            'resources/crontab/disable.sh.template',
            'resources/crontab/enable.sh.template',
            'resources/pm/initd/initd.template',
            'resources/pm/initd/initd.conf.template',
            'resources/pm/detach/detach.template',
            'resources/pm/detach/detach.conf.template',
            'resources/pm/nssm/nssm.exe',
            'resources/pm/nssm/nssm.conf.template',
            'resources/script/linux.sh.template',
            'resources/script/windows.ps1.template'
        ]
    },
    description='Cloudify Agent Implementation (Celery based)',
    install_requires=install_requires,
    license='LICENSE',
    entry_points={
        'console_scripts': [
            'cfy-agent = cloudify_agent.shell.main:main',
        ]
    }
)
