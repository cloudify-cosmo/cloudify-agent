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
    params['broker_ssl_cert_path'] = ssl_cert.local_cert_path()
    return Daemon(**params)


def test_default_workdir(agent_ssl_cert):
    assert os.path.join(os.getcwd(), 'work') == \
        get_daemon(agent_ssl_cert).workdir


def test_default_min_workers(agent_ssl_cert):
    assert 0 == get_daemon(agent_ssl_cert).min_workers


def test_default_max_workers(agent_ssl_cert):
    assert 5 == get_daemon(agent_ssl_cert).max_workers


def test_default_user(agent_ssl_cert):
    assert getpass.getuser() == get_daemon(agent_ssl_cert).user


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
