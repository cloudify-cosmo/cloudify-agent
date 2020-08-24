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

# before 5.1, these functions lived here. Re-import for backwards compat.
from cloudify.plugin_installer import (
    install,
    uninstall,
    get_managed_plugin,
    get_plugin_source,
    get_plugin_args,
    extract_package_to_dir
)

__all__ = ['install', 'uninstall', 'get_managed_plugin', 'get_plugin_source',
           'get_plugin_args', 'extract_package_to_dir']
