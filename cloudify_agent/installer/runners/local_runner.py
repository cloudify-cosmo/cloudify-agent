#########
# Copyright (c) 2016 GigaSpaces Technologies Ltd. All rights reserved
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

import tempfile

from cloudify.exceptions import HttpException
from cloudify.utils import LocalCommandRunner as _UtilsLocalCommandRunner

import requests


class LocalCommandRunner(_UtilsLocalCommandRunner):
    def download(self, url, output_path=None, skip_verification=False,
                 certificate_file=None, **attributes):
        verify = not skip_verification
        if certificate_file:
            verify = certificate_file
        response = requests.get(url, stream=True, verify=verify)
        if not response.ok:
            raise HttpException(url, response.status_code, response.reason)

        if output_path:
            destination_file = open(output_path, 'wb')
            destination = output_path
        else:
            destination_file = tempfile.NamedTemporaryFile(delete=False)
            destination = destination_file.name

        with destination_file:
            for chunk in response.iter_content(chunk_size=8192):
                destination_file.write(chunk)

        return destination
