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

import os
import logging

from fabric import network
from fabric import api as fabric_api
from fabric.context_managers import settings
from fabric.context_managers import hide
from fabric.context_managers import shell_env

from cloudify.utils import CommandExecutionResponse
from cloudify.utils import setup_logger
from cloudify.exceptions import CommandExecutionException
from cloudify.exceptions import CommandExecutionError

from cloudify_agent.installer import exceptions
from cloudify_agent.api import utils as api_utils

from cloudify_rest_client.utils import is_kerberos_env

DEFAULT_REMOTE_EXECUTION_PORT = 22
RSA_PRIVATE_KEY_PREFIX = '-----BEGIN RSA PRIVATE KEY-----'

COMMON_ENV = {
    'warn_only': True,
    'forward_agent': True,
    'abort_on_prompts': True,
    # Raise Exception(message) instead of calling sys.exit(1)
    'abort_exception': Exception,
    'disable_known_hosts': True
}


class FabricRunner(object):

    def __init__(self,
                 logger=None,
                 host=None,
                 user=None,
                 key=None,
                 port=None,
                 password=None,
                 validate_connection=True,
                 fabric_env=None):

        # logger
        self.logger = logger or setup_logger('fabric_runner')

        # silence paramiko
        logging.getLogger('paramiko.transport').setLevel(logging.WARNING)

        # connection details
        self.port = port or DEFAULT_REMOTE_EXECUTION_PORT
        self.password = password
        self.user = user
        self.host = host
        self.key = key

        # fabric environment
        self.env = self._set_env()
        self.env.update(fabric_env or {})

        self._validate_ssh_config()
        if validate_connection:
            self.validate_connection()

    def _validate_ssh_config(self):
        if not self.host:
            raise exceptions.AgentInstallerConfigurationError('Missing host')
        if not self.user:
            raise exceptions.AgentInstallerConfigurationError('Missing user')
        if not self.password and not self.key:
            raise exceptions.AgentInstallerConfigurationError(
                'Must specify either key or password')

    def _set_env(self):
        env = {
            'host_string': self.host,
            'port': self.port,
            'user': self.user
        }
        if self.key:
            if self.key.startswith(RSA_PRIVATE_KEY_PREFIX):
                env['key'] = self.key
            else:
                env['key_filename'] = self.key
        if self.password:
            env['password'] = self.password
        if is_kerberos_env():
            # For GSSAPI, the fabric env just needs to have
            # gss_auth and gss_kex set to True
            env['gss_auth'] = True
            env['gss_kex'] = True

        env.update(COMMON_ENV)
        return env

    def validate_connection(self):
        self.logger.debug('Validating SSH connection')
        self.ping()
        self.logger.debug('SSH connection is ready')

    def run(self, command, execution_env=None, **attributes):

        """
        Execute a command.

        :param command: The command to execute.
        :param execution_env: environment variables to be applied before
                              running the command
        :param quiet: run the command silently
        :param attributes: custom attributes passed directly to
                           fabric's run command

        :return: a response object containing information
                 about the execution
        :rtype: FabricCommandExecutionResponse
        """

        if execution_env is None:
            execution_env = {}

        with shell_env(**execution_env):
            with settings(**self.env):
                try:
                    with hide('warnings'):
                        r = fabric_api.run(
                            command,
                            quiet=not self.logger.isEnabledFor(logging.DEBUG),
                            **attributes)
                    if r.return_code != 0:

                        # by default, fabric combines the stdout
                        # and stderr streams into the stdout stream.
                        # this is good because normally when an error
                        # happens, the stdout is useful as well.
                        # this is why we populate the error
                        # with stdout and not stderr
                        # see http://docs.fabfile.org/en/latest
                        # /usage/env.html#combine-stderr
                        raise FabricCommandExecutionException(
                            command=command,
                            error=r.stdout,
                            output=None,
                            code=r.return_code
                        )
                    return FabricCommandExecutionResponse(
                        command=command,
                        std_out=r.stdout,
                        std_err=None,
                        return_code=r.return_code
                    )
                except FabricCommandExecutionException:
                    raise
                except BaseException as e:
                    raise FabricCommandExecutionError(
                        command=command,
                        error=str(e)
                    )

    def sudo(self, command, **attributes):

        """
        Execute a command under sudo.

        :param command: The command to execute.
        :param attributes: custom attributes passed directly to
                           fabric's run command

        :return: a response object containing information
                 about the execution
        :rtype: FabricCommandExecutionResponse
        """

        return self.run('sudo {0}'.format(command), **attributes)

    def run_script(self, script):
        """
        Execute a script.

        :param script: The path to the script to execute.
        :return: a response object containing information
                 about the execution
        :rtype: FabricCommandExecutionResponse
        :raise: FabricCommandExecutionException
        """

        remote_path = self.put_file(script)
        try:
            self.sudo('chmod +x {0}'.format(remote_path))
            result = self.sudo(remote_path)
        finally:
            # The script is pushed to a remote directory created with mkdtemp.
            # Hence, to cleanup the whole directory has to be removed.
            self.delete(os.path.dirname(remote_path))
        return result

    def put_file(self, src, dst=None, sudo=False, **attributes):

        """
        Copies a file from the src path to the dst path.

        :param src: Path to a local file.
        :param dst: The remote path the file will copied to.
        :param sudo: indicates that this operation
                     will require sudo permissions
        :param attributes: custom attributes passed directly to
                           fabric's run command

        :return: the destination path
        """

        if dst:
            self.verify_dir_exists(os.path.dirname(dst))
        else:
            basename = os.path.basename(src)
            tempdir = self.mkdtemp()
            dst = os.path.join(tempdir, basename)

        with settings(**self.env):
            with hide('warnings'):
                r = fabric_api.put(src, dst, use_sudo=sudo, **attributes)
                if not r.succeeded:
                    raise FabricCommandExecutionException(
                        command='fabric_api.put',
                        error='Failed uploading {0} to {1}'
                        .format(src, dst),
                        code=-1,
                        output=None
                    )
        return dst

    def ping(self, **attributes):

        """
        Tests that the connection is working.

        :param attributes: custom attributes passed directly to
                           fabric's run command

        :return: a response object containing information
                 about the execution
        :rtype: FabricCommandExecutionResponse
        """

        return self.run('echo', **attributes)

    def mktemp(self, create=True, directory=False, **attributes):

        """
        Creates a temporary path.

        :param create: actually create the file or just construct the path
        :param directory: path should be a directory or not.
        :param attributes: custom attributes passed directly to
                           fabric's run command

        :return: the temporary path
        """

        flags = []
        if not create:
            flags.append('-u')
        if directory:
            flags.append('-d')
        return self.run('mktemp {0}'
                        .format(' '.join(flags)),
                        **attributes).std_out.rstrip()

    def mkdtemp(self, create=True, **attributes):

        """
        Creates a temporary directory path.

        :param create: actually create the file or just construct the path
        :param attributes: custom attributes passed directly to
                           fabric's run command

        :return: the temporary path
        """

        return self.mktemp(create=create, directory=True, **attributes)

    def home_dir(self, username):

        """
        Retrieve the path of the user's home directory.

        :param username: the username

        :return: path to the home directory
        """
        return self.python(
            imports_line='import pwd',
            command='pwd.getpwnam(\'{0}\').pw_dir'
            .format(username))

    def verify_dir_exists(self, dirname):
        self.run('mkdir -p {0}'.format(dirname))

    def python(self, imports_line, command, **attributes):

        """
        Run a python command and return the output.

        To overcome the situation where additional info is printed
        to stdout when a command execution occurs, a string is
        appended to the output. This will then search for the string
        and the following closing brackets to retrieve the original output.

        :param imports_line: The imports needed for the command.
        :param command: The python command to run.
        :param attributes: custom attributes passed directly to
                           fabric's run command

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
                                  command), **attributes).std_out
        result = stdout[stdout.find(start) - 1 + len(end):
                        stdout.find(end)]
        return result

    def machine_distribution(self, **attributes):

        """
        Retrieves the distribution information of the host.

        :param attributes: custom attributes passed directly to
                           fabric's run command

        :return: dictionary of the platform distribution as returned from
                 'platform.dist()'

        """

        response = self.python(
            imports_line='import platform, json',
            command='json.dumps(platform.dist())', **attributes
        )
        return api_utils.json_loads(response)

    def delete(self, path):
        self.run('rm -rf {0}'.format(path))

    @staticmethod
    def close():

        """
        Closes all fabric connections.

        """

        network.disconnect_all()


class FabricCommandExecutionError(CommandExecutionError):

    """
    Indicates a failure occurred while trying to execute the command.

    """

    pass


class FabricCommandExecutionException(CommandExecutionException):

    """
    Indicates the command was executed but a failure occurred.

    """
    pass


class FabricCommandExecutionResponse(CommandExecutionResponse):

    """
    Wrapper for indicating the command was originated with fabric api.
    """
    pass
