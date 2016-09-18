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

"""
This module maintains backwards compatibility with Compute node types
version < 3.3.
"""

from cloudify.decorators import operation
from cloudify_agent.installer import operations


@operation
def install(**kwargs):
    _fix_winrm_port_for_old_windows_blueprints(kwargs)
    operations.create(**kwargs)
    operations.configure(**kwargs)


@operation
def start(**kwargs):
    _fix_winrm_port_for_old_windows_blueprints(kwargs)
    operations.start(**kwargs)


@operation
def stop(**kwargs):
    _fix_winrm_port_for_old_windows_blueprints(kwargs)
    operations.stop(**kwargs)


@operation
def restart(**kwargs):
    _fix_winrm_port_for_old_windows_blueprints(kwargs)
    operations.restart(**kwargs)


@operation
def uninstall(**kwargs):
    _fix_winrm_port_for_old_windows_blueprints(kwargs)
    operations.delete(**kwargs)


def _fix_winrm_port_for_old_windows_blueprints(kwargs):
    cloudify_agent = kwargs.get('cloudify_agent') or {}
    agent_config = kwargs.get('agent_config') or {}
    cloudify_agent.update(agent_config)
    cloudify_agent.setdefault('windows', True)
    cloudify_agent.setdefault('port', 5985)
    kwargs['cloudify_agent'] = cloudify_agent
