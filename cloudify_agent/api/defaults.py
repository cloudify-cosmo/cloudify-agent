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

START_TIMEOUT = 15
START_INTERVAL = 1
STOP_TIMEOUT = 15
STOP_INTERVAL = 1
MANAGER_PORT = 80
BROKER_PORT = 5672
DISABLE_REQUIRETTY = False
RELOCATED = False
MIN_WORKERS = 0
MAX_WORKERS = 5
BROKER_URL = 'amqp://guest:guest@{0}:{1}//'
DELETE_AMQP_QUEUE_BEFORE_START = False
DAEMON_FORCE_DELETE = False
CLOUDIFY_AGENT_PREFIX = 'cloudify-agent'
