import pytest

from cloudify_agent.installer.runners import winrm_runner
from cloudify_agent.installer.runners.winrm_runner import split_into_chunks

##############################################################################
# note that this file only tests validation and defaults of the winrm runner.
# it does not test the actual functionality because that requires starting
# a vm. functional tests are executed as local workflow tests in the system
# tests framework
##############################################################################


def test_validate_host():
    # Missing host
    session_config = {
        'user': 'test_user',
        'password': 'test_password'
    }
    with pytest.raises(ValueError, match='.*Invalid host.*'):
        winrm_runner.validate(session_config)


def test_validate_user():
    # Missing user
    session_config = {
        'host': 'test_host',
        'password': 'test_password'
    }
    with pytest.raises(ValueError, match='.*Invalid user.*'):
        winrm_runner.validate(session_config)


def test_validate_password():
    # Missing password
    session_config = {
        'host': 'test_host',
        'user': 'test_user'
    }
    with pytest.raises(ValueError, match='.*Invalid password.*'):
        winrm_runner.validate(session_config)


def test_defaults():
    runner = winrm_runner.WinRMRunner(
        validate_connection=False,
        host='test_host',
        user='test_user',
        password='test_password')

    assert runner.session_config['protocol'] == \
        winrm_runner.DEFAULT_WINRM_PROTOCOL
    assert runner.session_config['uri'] == \
        winrm_runner.DEFAULT_WINRM_URI
    assert runner.session_config['port'] == \
        winrm_runner.DEFAULT_WINRM_PORT
    assert runner.session_config['transport'] == \
        winrm_runner.DEFAULT_TRANSPORT


def test_empty_string():
    """An empty string is not splitted."""
    contents = ''
    expected_chunks = ['']
    assert split_into_chunks(contents) == expected_chunks


def test_one_line():
    """A single is not splitted."""
    contents = 'this is a string'
    expected_chunks = [contents]
    assert split_into_chunks(contents) == expected_chunks


def test_multiple_lines():
    """Multiple lines are splitted as expected."""
    contents = 'a\nfew\nshort\nlines'
    expected_chunks = ['a\nfew', 'short', 'lines']
    assert split_into_chunks(contents, max_size=10, separator='\n') == \
        expected_chunks


def test_line_too_long():
    """Exception raised on line too long."""
    contents = 'a very long line'
    pytest.raises(ValueError, split_into_chunks, contents, max_size=1)
