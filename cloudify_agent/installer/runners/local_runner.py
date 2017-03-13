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

import os
import shutil
import tempfile

import requests

from cloudify.state import ctx
from cloudify.exceptions import HttpException
from cloudify.constants import CLOUDIFY_TOKEN_AUTHENTICATION_HEADER
from cloudify.utils import LocalCommandRunner as _UtilsLocalCommandRunner


class LocalCommandRunner(_UtilsLocalCommandRunner):
    def download(self, url, output_path=None, certificate_file=None,
                 **attributes):
        headers = {CLOUDIFY_TOKEN_AUTHENTICATION_HEADER: str(ctx.rest_token)}
        response = requests.get(
            url, stream=True, verify=certificate_file, headers=headers)
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

    def put_file(self, src, dst=None, *_):
        if dst:
            # Create any directories that don't already exist
            os.makedirs(os.path.dirname(dst))
        else:
            basename = os.path.basename(src)
            tempdir = tempfile.mkdtemp()
            dst = os.path.join(tempdir, basename)
        shutil.copy2(src, dst)
