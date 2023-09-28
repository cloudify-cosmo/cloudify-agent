#########
# Copyright (c) 2015-2019 Cloudify Platform Ltd. All rights reserved
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
    'cloudify-common',
    'appdirs==1.4.3',
    'jinja2>3,<4',
    'click>8,<9',
    'packaging',
    'requests>=2.25.0,<3.0.0',
]


setup(
    name='cloudify-agent',
    version='7.0.3.dev1',
    author='Cloudify',
    author_email='cosmo-admin@cloudify.co',
    packages=[
        'worker_installer',
        'windows_agent_installer',
        'plugin_installer',
        'windows_plugin_installer',
        'cloudify_agent',
        'cloudify_agent.api',
        'cloudify_agent.api.pm',
        'cloudify_agent.api.plugins',
        'cloudify_agent.installer',
        'cloudify_agent.installer.config',
        'cloudify_agent.installer.runners',
        'cloudify_agent.shell',
        'cloudify_agent.shell.commands',
        'diamond_agent',  # Stub for back compat
    ],
    package_data={
        'cloudify_agent': [
            'VERSION',
            'resources/disable-requiretty.sh',
            'resources/crontab/disable.sh.template',
            'resources/crontab/enable.sh.template',
            'resources/respawn.sh.template',
            'resources/pm/initd/initd.conf.template',
            'resources/pm/initd/initd.template',
            'resources/pm/detach/detach.conf.template',
            'resources/pm/detach/detach.template',
            'resources/pm/nssm/nssm.exe',
            'resources/pm/nssm/nssm.conf.template',
            'resources/pm/systemd/systemd.conf.template',
            'resources/pm/systemd/systemd.template',
            'resources/script/linux.sh.template',
            'resources/script/windows.ps1.template',
            'resources/script/linux-download.sh.template',
            'resources/script/windows-download.ps1.template',
            'resources/script/stop-agent.py.template'
        ]
    },
    description='Cloudify Agent Implementation (pika based)',
    install_requires=install_requires,
    license='LICENSE',
    entry_points={
        'console_scripts': [
            'cfy-agent = cloudify_agent.shell.main:main',
            'worker = cloudify_agent.worker:main'
        ]
    },
    extras_require={
        'kerberos': [
            'pywinrm[Kerberos]==0.4.1',
            'python-gssapi==0.6.4',
            'cffi>=1.14,<1.15',
        ],
        'celery': [
            'celery==4.4.7',
        ],
        'fabric': [
            'fabric==2.5.0',
            'pynacl==1.4.0',
            'invoke==1.6.0',
        ]
    }
)
