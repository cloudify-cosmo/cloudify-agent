import getpass
import os

import pytest

from cloudify_agent.api.pm.base import Daemon
from cloudify_agent.api import exceptions


def get_daemon(ssl_cert, params=None):
    if not params:
        params = {
            'rest_host': '127.0.0.1',
            'broker_ip': '127.0.0.1',
        }
    params['queue'] = 'queue'
    params['name'] = 'queue'
    params['broker_user'] = 'guest'
    params['broker_pass'] = 'guest'
    params['local_rest_cert_file'] = ssl_cert.local_cert_path()
    return Daemon(**params)


def test_default_workdir(agent_ssl_cert):
    assert os.getcwd() == get_daemon(agent_ssl_cert).workdir


def test_default_rest_port(agent_ssl_cert):
    assert 53333 == get_daemon(agent_ssl_cert).rest_port


def test_default_min_workers(agent_ssl_cert):
    assert 0 == get_daemon(agent_ssl_cert).min_workers


def test_default_max_workers(agent_ssl_cert):
    assert 5 == get_daemon(agent_ssl_cert).max_workers


def test_default_user(agent_ssl_cert):
    assert getpass.getuser() == get_daemon(agent_ssl_cert).user


def test_missing_rest_host(agent_ssl_cert):
    with pytest.raises(exceptions.DaemonMissingMandatoryPropertyError,
                       match='.*rest_host is mandatory.*'):
        get_daemon(agent_ssl_cert, params={
            'host': 'queue',
            'user': 'user',
        })


def test_bad_min_workers(agent_ssl_cert):
    with pytest.raises(exceptions.DaemonPropertiesError,
                       match='.*min_workers is supposed to be a number.*'):
        get_daemon(agent_ssl_cert, params={
            'host': 'queue',
            'rest_host': '127.0.0.1',
            'broker_ip': '127.0.0.1',
            'user': 'user',
            'min_workers': 'bad',
        })


def test_bad_max_workers(agent_ssl_cert):
    with pytest.raises(exceptions.DaemonPropertiesError,
                       match='.*max_workers is supposed to be a number.*'):
        get_daemon(agent_ssl_cert, params={
            'host': 'queue',
            'rest_host': '127.0.0.1',
            'broker_ip': '127.0.0.1',
            'user': 'user',
            'max_workers': 'bad',
        })


def test_min_workers_larger_than_max_workers(agent_ssl_cert):
    with pytest.raises(
        exceptions.DaemonPropertiesError,
        match='.*min_workers cannot be greater than max_workers.*',
    ):
        get_daemon(agent_ssl_cert, params={
            'host': 'queue',
            'rest_host': '127.0.0.1',
            'broker_ip': '127.0.0.1',
            'user': 'user',
            'max_workers': 4,
            'min_workers': 5,
        })


def test_start_command(agent_ssl_cert):
    pytest.raises(NotImplementedError,
                  get_daemon(agent_ssl_cert).start_command)


def test_stop_command(agent_ssl_cert):
    pytest.raises(NotImplementedError,
                  get_daemon(agent_ssl_cert).stop_command)


def test_configure(agent_ssl_cert):
    pytest.raises(NotImplementedError, get_daemon(agent_ssl_cert).configure)


def test_delete(agent_ssl_cert):
    pytest.raises(NotImplementedError, get_daemon(agent_ssl_cert).delete)
