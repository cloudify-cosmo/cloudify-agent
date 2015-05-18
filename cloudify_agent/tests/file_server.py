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


import subprocess
import SimpleHTTPServer
import SocketServer
import os
import sys
import socket
import time
from multiprocessing import Process

from cloudify.utils import setup_logger
from cloudify import exceptions

PORT = 53229
FNULL = open(os.devnull, 'w')


logger = setup_logger('cloudify_agent.tests.file_server')


class FileServer(object):

    def __init__(self, root_path, use_subprocess=True, timeout=5, port=PORT):
        self.root_path = root_path
        self.use_subprocess = use_subprocess
        self.timeout = timeout
        self.port = port

    def start(self):
        logger.info('Starting file server [subprocess={0}, __name__={1}]'
                    .format(self.use_subprocess, __name__))
        if self.use_subprocess:
            self.process = subprocess.Popen(
                [sys.executable, '-m', 'SimpleHTTPServer', str(self.port)],
                stdin=FNULL,
                stdout=None,
                stderr=None,
                cwd=self.root_path)
        else:
            self.process = Process(target=self.start_impl)
            self.process.start()

        end_time = time.time() + self.timeout

        while end_time > time.time():
            if self.is_alive():
                logger.info('File server is up and serving from {0}'
                            .format(self.root_path))
                return
            logger.info('File server is not responding. waiting 10ms')
            time.sleep(0.1)
        raise exceptions.TimeoutException('Failed starting '
                                          'file server in {0} seconds'
                                          .format(self.timeout))

    def stop(self):
        try:
            logger.info('Shutting down file server')
            self.process.terminate()
            while self.is_alive():
                logger.info('File server is still up. waiting for 10ms')
                time.sleep(0.1)
            logger.info('File server has shut down')
        except BaseException as e:
            logger.warning(str(e))

    def start_impl(self):
        class TCPServer(SocketServer.TCPServer):
            allow_reuse_address = True
        httpd = TCPServer(('0.0.0.0', self.port),
                          SimpleHTTPServer.SimpleHTTPRequestHandler)
        httpd.serve_forever()

    def is_alive(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(('localhost', self.port))
            s.close()
            return True
        except socket.error:
            return False


if __name__ == '__main__':
    FileServer(sys.argv[1]).start_impl()
