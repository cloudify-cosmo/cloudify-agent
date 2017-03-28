#########
# Copyright (c) 2015 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

import winrm
import ntpath

from cloudify import ctx
from cloudify.exceptions import CommandExecutionException
from cloudify.exceptions import CommandExecutionError
from cloudify.utils import CommandExecutionResponse
from cloudify.utils import setup_logger
from cloudify.constants import CLOUDIFY_TOKEN_AUTHENTICATION_HEADER

from cloudify_agent.installer import utils
from cloudify_agent.api import utils as api_utils

DEFAULT_WINRM_PORT = '5985'
DEFAULT_WINRM_URI = 'wsman'
DEFAULT_WINRM_PROTOCOL = 'http'


def validate(session_config):

    def _validate(prop):
        value = session_config.get(prop)
        if not value:
            raise ValueError('Invalid {0}: {1}'
                             .format(prop, value))

    _validate('host')
    _validate('user')
    _validate('password')


class WinRMRunner(object):

    def __init__(self,
                 user,
                 password,
                 protocol=None,
                 host=None,
                 port=None,
                 uri=None,
                 validate_connection=True,
                 logger=None):

        logger = logger or setup_logger('WinRMRunner')

        self.session_config = {
            'protocol': protocol or DEFAULT_WINRM_PROTOCOL,
            'host': host,
            'port': port or DEFAULT_WINRM_PORT,
            'uri': uri or DEFAULT_WINRM_URI,
            'user': user,
            'password': password
        }

        # Validations - [host, user, password]
        validate(self.session_config)

        self.session = self._create_session()
        self.logger = logger

        if validate_connection:
            self.validate_connection()

    def validate_connection(self):
        self.logger.debug('Validating WinRM connection')
        self.ping()
        self.logger.debug('WinRM connection is ready')

    def _create_session(self):

        winrm_url = '{0}://{1}:{2}/{3}'.format(
            self.session_config['protocol'],
            self.session_config['host'],
            self.session_config['port'],
            self.session_config['uri'])
        return winrm.Session(
            target=winrm_url,
            auth=(self.session_config['user'],
                  self.session_config['password']))

    def run(self, command, raise_on_failure=True, execution_env=None,
            powershell=False):

        """
        :param command: The command to execute.
        :param raise_on_failure: by default, this will raise an exception
                                 if the command fails. You can use
                                 raise_on_failure=False to just log the
                                 error and not raise an exception.
        :param execution_env: environment variables to be applied before
                              running the command
        :param powershell: Determines where to run command as a powershell
                           script.

        :return a response object with information about the execution
        :rtype WinRMCommandExecutionResponse.
        """

        if execution_env is None:
            execution_env = {}

        remote_env_file = None
        if execution_env:
            env_file = utils.env_to_file(execution_env, posix=False)
            remote_env_file = self.put_file(src=env_file,
                                            dst='{0}.bat'.format(
                                                self.mktemp()))

        def _chk(res):
            if res.status_code == 0:
                return WinRMCommandExecutionResponse(
                    command=command,
                    std_err=res.std_err,
                    std_out=res.std_out,
                    return_code=res.status_code)
            else:
                error = WinRMCommandExecutionException(
                    command=command,
                    code=res.status_code,
                    error=res.std_err,
                    output=res.std_out)
                if raise_on_failure:
                    raise error
                self.logger.error(error)

        self.logger.debug(
            '[{0}] run: {1}'.format(
                self.session_config['host'],
                command))

        if remote_env_file:
            command = 'call {0} & {1}'.format(remote_env_file, command)
        try:
            if powershell:
                response = self.session.run_ps(command)
            else:
                response = self.session.run_cmd(command)
        except BaseException as e:
            raise WinRMCommandExecutionError(
                command=command,
                error=str(e)
            )
        return _chk(response)

    def ping(self):

        """
        Tests that the winrm connection is working.

        :return a response object with information about the execution
        :rtype WinRMCommandExecutionResponse.
        """

        return self.run('echo')

    def download(self, url, output_path=None, certificate_file=None):

        """
        :param url: URL to the resource to download.
        :param output_path: Local path the resource will be saved as.
        :param certificate_file: a local cert file to use for SSL certificate
               verification.

        :return the destination path the url was downloaded to.
        """

        if output_path is None:
            output_path = self.mktemp()

        if certificate_file:
            self.logger.info('Adding certificate to cert root: "{0}"'.format(
                certificate_file))
            cmd = """
Import-Certificate -FilePath "{0}" -CertStoreLocation Cert:\LocalMachine\Root
""".format(certificate_file)
            self.run(cmd, powershell=True)

        self.logger.info('Downloading {0}'.format(url))
        cmd = """
$webClient = New-Object System.Net.WebClient
$webClient.Headers['{0}'] = '{1}'
$webClient.Downloadfile('{2}', '{3}')""".format(
            CLOUDIFY_TOKEN_AUTHENTICATION_HEADER,
            ctx.rest_token,
            url,
            output_path)

        # downloading agent package from the manager
        self.run(cmd, powershell=True)

        return output_path

    def move(self, src, dst):

        """
        Moves item at <src> to <dst>.

        :param src: Path to the source item.
        :param dst: Path to the destination item.

        :return a response object with information about the execution
        :rtype WinRMCommandExecutionResponse.
        """

        return self.run(
            '''@powershell -Command "Move-Item {0} {1}"'''
            .format(src, dst))

    def copy(self, src, dst, force=False):

        """
        Copies item at <src> to <dst>.

        :param src: Path to the source item.
        :param dst: Path to the destination item.
        :param force: Creates missing path if needed.

        :return a response object with information about the execution
        :rtype WinRMCommandExecutionResponse.
        """

        if force:
            return self.run(
                '''@powershell -Command "Copy-Item -Recurse -Force {0} {1}"'''
                .format(src, dst))
        return self.run(
            '''@powershell -Command "Copy-Item -Recurse {0} {1}"'''  # NOQA
            .format(src, dst))

    def exists(self, path):

        """
        Test if the given path exists.

        :param path: The path to tests.

        :return whether or not the path exists
        """

        response = self.run(
            '''@powershell -Command "Test-Path {0}"'''  # NOQA
            .format(path))
        return response.std_out == 'True\r\n'

    def delete(self, path, ignore_missing=False):

        """
        Deletes the resource in the given path.

        :param path: The path do delete. Can be either a file or a folder.

        :return a response object with information about the execution
        :rtype WinRMCommandExecutionResponse.
        """

        return self.run(
            """@powershell -Command 'Remove-Item -Recurse -Force "{0}"'"""
            .format(path), raise_on_failure=not ignore_missing)

    def mktemp(self):

        """
        Creates a temporary path.

        :return: the temporary path
        """

        return self.run(
            '''@powershell -Command "[System.IO.Path]::GetTempFileName()"'''
        ).std_out.strip()

    def new_dir(self, path):

        """
        Creates the path as a new directory.

        :param path: The directory path to create.

        :return a response object with information about the execution
        :rtype WinRMCommandExecutionResponse.
        """

        return self.run('mkdir \"{0}\" -Force'.format(path), powershell=True)

    def new_file(self, path):

        """
        Creates the path as a new file.

        :param path: The file path to create.

        :return a response object with information about the execution
        :rtype WinRMCommandExecutionResponse.
        """

        return self.run(
            '''@powershell -Command "New-Item {0} -type file"'''
            .format(path))

    def service_state(self, service_name):

        """
        Queries the state of the given service.

        :param service_name: The service name to query.

        :return

            The state of the service.
                - 'Running'
                - 'Stopped'
                - 'Start Pending'
                - 'Continue Pending'
                - 'Pause Pending'
                - 'Paused'
                - 'Unknown'

        :return the state of the service.
        """

        response = self.run(
            '''@powershell -Command "(Get-Service -Name {0}).Status"'''  # NOQA
            .format(service_name))
        return response.std_out.strip()

    def machine_distribution(self):

        """
        Retrieves the distribution information of the host.

        :return: dictionary of the platform distribution as returned from
        'platform.dist()'
        """

        response = self.python(
            imports_line='import platform, json',
            command='json.dumps(platform.dist())'
        )
        return api_utils.json_loads(response)

    def python(self, imports_line, command):

        """
        Run a python command and return the output.

        To overcome the situation where additional info is printed
        to stdout when a command execution occurs, a string is
        appended to the output. This will then search for the string
        and the following closing brackets to retrieve the original output.

        :param imports_line: The imports needed for the command.
        :param command: The python command to run.

        :return: the string representation of the return value of
                 the python command
        """

        start = '###CLOUDIFYCOMMANDOPEN'
        end = 'CLOUDIFYCOMMANDCLOSE###'

        stdout = self.run('python -c "import sys; {0}; '
                          'sys.stdout.write(\'{1}{2}{3}\\n\''
                          '.format({4}))"'
                          .format(imports_line,
                                  start,
                                  '{0}',
                                  end,
                                  command)).std_out
        result = stdout[stdout.find(start) - 1 + len(end):
                        stdout.find(end)]
        return result

    def put(self, contents, path):

        """
        Writes the contents to a file in the given path.

        :param contents: The contents to write. string based.
        :param path: Path to a file.
                     The file must be inside an existing directory.

        :return a response object with information about the execution
        :rtype WinRMCommandExecutionResponse.
        """
        contents = contents.replace(
            '\r', '`r').replace(
            '\n', '`n').replace(
            ' ',  '` ').replace(
            "'",  "`'").replace(
            '"',  '`"').replace(
            '\t', '`t')
        return self.run('Set-Content "{0}" "{1}"'.format(
                path, contents), powershell=True)

    def get(self, path):

        """
        Reads the contents of the file in the given path.

        :param path: Path to a file.

        :return the content of the file in the given path.
        """

        return self.run(
            '''@powershell -Command "Get-Content {0}"'''
            .format(path)).std_out

    def unzip(self, archive, destination):

        """
        Un-tars an archive. internally this will use the 'tar' command line,
        so any archive supported by it is ok.

        :param archive: path to the archive.
        :param destination: destination directory

        :return a response object with information about the execution
        :rtype WinRMCommandExecutionResponse.
        """

        self.run(
            '''@powershell -Command "Add-Type -assembly \
"system.io.compression.filesystem""'''
        )
        return self.run(
            '''@powershell -Command \
"[io.compression.zipfile]::ExtractToDirectory({0}, {1})"'''
            .format(archive, destination))

    def put_file(self, src, dst=None):

        """
        Copies a file from the src path on the host machine to the dst path
        on the target machine

        :param src: Path to a local file.
        :param dst: The remote path the file will copied to.

        :return: the destination path
        """

        with open(src) as f:
            content = f.read()

        if dst:
            # Make sure the destination folder exists
            self.new_dir(ntpath.dirname(dst))
        else:
            dst = self.mktemp()
        self.put(contents=content, path=dst)
        return dst

    def close(self):
        pass


class WinRMCommandExecutionError(CommandExecutionError):

    """
    Indicates a failure occurred while trying to execute the command.

    """

    pass


class WinRMCommandExecutionException(CommandExecutionException):

    """
    Indicates a failure to execute a command over WinRM.

    """
    pass


class WinRMCommandExecutionResponse(CommandExecutionResponse):

    """
    Wrapper for indicating the command was originated from a winrm session.
    """
    pass
