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

from cloudify_agent.api.pm.base import CronSupervisorMixin


class DetachedDaemon(CronSupervisorMixin):

    """
    This process management is not really a full process management. It
    merely runs the celery commands in detached mode and uses crontab for
    re-spawning the daemon on failure. The advantage of this kind of daemon
    is that it does not require privileged permissions to execute.
    """

    def configure(self):
        pass
