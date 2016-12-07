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
import sys

from cloudify import ctx
from cloudify.utils import LocalCommandRunner
from cloudify.decorators import operation


@operation
def run(**_):
    return 'run'


@operation
def get_env_variable(env_variable, **_):
    return os.environ[env_variable]


@operation
def do_logging(message, **_):
    ctx.logger.info(message)


@operation
def call_entry_point(**_):
    runner = LocalCommandRunner()
    return runner.run('mock-plugin-entry-point').std_out


def main():
    sys.stdout.write('mock-plugin-entry-point')


if __name__ == '__main__':
    main()
