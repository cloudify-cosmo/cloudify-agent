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

try:
    import winrm
except Exception:
    winrm = None
import ntpath

from cloudify.exceptions import CommandExecutionException
from cloudify.exceptions import CommandExecutionError
from cloudify.utils import CommandExecutionResponse
from cloudify.utils import setup_logger

from cloudify_agent.installer import utils
from cloudify_agent.api import utils as api_utils

from cloudify_rest_client.utils import is_kerberos_env

DEFAULT_WINRM_PORT = '5985'
DEFAULT_WINRM_URI = 'wsman'
DEFAULT_WINRM_PROTOCOL = 'http'
DEFAULT_TRANSPORT = 'basic'


def validate(session_config):

    def _validate(prop):
        value = session_config.get(prop)
        if not value:
            raise ValueError('Invalid {0}: {1}'
                             .format(prop, value))

    _validate('host')
    _validate('user')
    if not is_kerberos_env():
        # no need to supply password in Kerberos env
        _validate('password')


class WinRMRunner(object):

    def __init__(self,
                 user,
                 password=None,
                 protocol=None,
                 host=None,
                 port=None,
                 uri=None,
                 transport=None,
                 validate_connection=True,
                 logger=None,
                 tmpdir=None):

        logger = logger or setup_logger('WinRMRunner')

        self.session_config = {
            'protocol': protocol or DEFAULT_WINRM_PROTOCOL,
            'host': host,
            'port': port or DEFAULT_WINRM_PORT,
            'uri': uri or DEFAULT_WINRM_URI,
            'user': user,
            'password': password,
            'transport': transport or DEFAULT_TRANSPORT
        }
        self.tmpdir = tmpdir

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
        if not winrm:
            raise CommandExecutionError(
                command='winrm',
                error='winrm not installed'
            )
        winrm_url = '{0}://{1}:{2}/{3}'.format(
            self.session_config['protocol'],
            self.session_config['host'],
            self.session_config['port'],
            self.session_config['uri'])
        if is_kerberos_env():
            # The change is simply setting the transport to kerberos
            # and setting the kerberos_hostname_override parameter
            # to the destination hostname.
            return winrm.Session(
                target=winrm_url,
                auth=(self.session_config['user'], None),
                transport='kerberos',
                kerberos_hostname_override=self.session_config['host'])
        else:
            return winrm.Session(
                target=winrm_url,
                auth=(self.session_config['user'],
                      self.session_config['password']),
                transport=self.session_config['transport'])

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
                self.logger.error("WinRM command ended with an error",
                                  error)

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

    def delete(self, path, ignore_missing=False):

        """
        Deletes the resource in the given path.

        :param path: The path do delete. Can be either a file or a folder.

        :return a response object with information about the execution
        :rtype WinRMCommandExecutionResponse.
        """

        return self.run(
            'Remove-Item -Recurse -Force "{0}"'.format(path),
            raise_on_failure=not ignore_missing,
            powershell=True,
        )

    def mktemp(self):

        """
        Creates a temporary path.

        :return: the temporary path
        """

        return self.run(
            '''@powershell -Command "[System.IO.Path]::GetTempFileName()"'''
        ).std_out.strip()

    def get_temp_dir(self):
        """Get remote temporary directory.

        :return: Temporary directory
        :rtype: str

        """
        if self.tmpdir is not None:
            return self.tmpdir
        return self.run(
            '@powershell -Command "[System.IO.Path]::GetTempPath()"'
        ).std_out.strip()

    def new_dir(self, path):

        """
        Creates the path as a new directory.

        :param path: The directory path to create.

        :return a response object with information about the execution
        :rtype WinRMCommandExecutionResponse.
        """

        return self.run('mkdir \"{0}\" -Force'.format(path), powershell=True)

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

        """Split contents into chunks and write them to file in the given path.

        :param contents: The contents to write. string based.
        :param path: Path to a file.
                     The file must be inside an existing directory.

        :return:
            a list of response objects with information about all executions
        :rtype WinRMCommandExecutionResponse.
        """
        # Escape single quotes, since the contents is surrounded by them
        contents = contents.replace("'", "''")
        chunks = split_into_chunks(contents)
        responses = [
            self.run(
                'Add-Content "{0}" \'{1}\''.format(path, chunk),
                powershell=True,
            )
            for chunk in chunks
        ]
        return responses

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

    def run_script(self, script_path):
        """Upload script to remote instances, execute it and delete it.

        :param script_path: Local path to script
        :type script_path: str
        :return: Script execution output
        :rtype WinRMCommandExecutionResponse

        """
        remote_path = ntpath.join(
            self.get_temp_dir(),
            ntpath.basename(script_path),
        )
        try:
            self.put_file(script_path, remote_path)
            result = self.run(remote_path, powershell=True)
        finally:
            self.delete(remote_path, ignore_missing=True)
        return result


def split_into_chunks(contents, max_size=2000, separator='\r\n'):
    """Split content into chunks to avoid command line too long error.

    Maximum allowed commmand line length should be 2047 in old windows:
    https://support.microsoft.com/en-us/help/830473/command-prompt-cmd--exe-command-line-string-limitation

    :param contents:
        The contents of a file that exceeds the maximum command line length in
        windows.
    :type content: str
    :returns: The same content in chunks that won't exceed the limit
    :rtype: list[str]

    """
    def join_lines(lines, line):
        if len(line) > max_size:
            raise ValueError('Line too long (%d characters)' % len(line))

        if (
            lines and
            len(lines[-1]) + len(line) + len(separator) <= max_size
        ):
            lines[-1] += '{0}{1}'.format(separator, line)
        else:
            lines.append(line)
        return lines

    if contents:
        chunks = reduce(join_lines, contents.splitlines(), [])
    else:
        chunks = ['']
    return chunks


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
