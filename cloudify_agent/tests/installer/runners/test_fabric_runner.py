from mock import Mock, patch
import pytest

from cloudify_agent.installer import exceptions

# these imports may run on a windows box, in which case they may fail. (if
# the pywin32 extensions). The tests wont run anyway because of the decorator,
# so we can just avoid this import.
try:
    from cloudify_agent.installer.runners.fabric_runner import FabricRunner
    from cloudify_agent.installer.runners.fabric_runner import (
        FabricCommandExecutionException,
    )
except ImportError:
    FabricRunner = None
    FabricCommandExecutionException = None

from cloudify_agent.tests.api.pm import only_os


##############################################################################
# note that this file only tests validation and defaults of the fabric runner.
# it does not test the actual functionality because that requires starting
# a vm. functional tests are executed as local workflow tests in the system
# tests framework
##############################################################################

@only_os('posix')
def test_default_port():
    runner = FabricRunner(
        validate_connection=False,
        user='user',
        host='host',
        password='password')
    assert runner.port == 22


@only_os('posix')
def test_no_host():
    with pytest.raises(exceptions.AgentInstallerConfigurationError,
                       match='.*Missing host.*'):
        FabricRunner(
            validate_connection=False,
            user='user',
            password='password'
        )


@only_os('posix')
def test_no_user():
    with pytest.raises(exceptions.AgentInstallerConfigurationError,
                       match='.*Missing user.*'):
        FabricRunner(
            validate_connection=False,
            host='host',
            password='password',
        )


@only_os('posix')
def test_no_key_no_password():
    with pytest.raises(exceptions.AgentInstallerConfigurationError,
                       match='.*Must specify either key or password.*'):
        FabricRunner(
            validate_connection=False,
            host='host',
            user='password',
        )


@only_os('posix')
def test_exception_message():
    """Exception message is the same one used by fabric."""
    expected_message = '<message>'

    runner = FabricRunner(
        validate_connection=False,
        user='user',
        host='host',
        password='password',
    )

    connection_path = (
        'cloudify_agent.installer.runners.fabric_runner.Connection'
    )
    with patch(connection_path) as conn_factory:
        conn_factory.return_value.run.return_value = Mock(
            return_code=1,
            stderr=expected_message
        )
        try:
            runner.run('a command')
        except FabricCommandExecutionException as e:
            assert e.error == expected_message
        else:
            pytest.fail('FabricCommandExecutionException not raised')
