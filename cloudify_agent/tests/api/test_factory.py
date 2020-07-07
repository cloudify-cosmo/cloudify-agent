import uuid
import os
import pytest
import shutil

from cloudify_agent.api import exceptions
from cloudify_agent.api import utils
from cloudify_agent.tests.utils import get_daemon_storage


def test_new_initd(daemon_factory, agent_ssl_cert):
    daemon_name = 'test-daemon-{0}'.format(uuid.uuid4())
    daemon = daemon_factory.new(
        **get_daemon_params(daemon_name, agent_ssl_cert))
    assert daemon_name == daemon.name
    assert 'queue' == daemon.queue
    assert '127.0.0.1' == daemon.rest_host
    assert 'user' == daemon.user
    assert agent_ssl_cert.get_local_cert_path() == daemon.local_rest_cert_file


def test_save_load_delete(daemon_factory, agent_ssl_cert):
    daemon_name = 'test-daemon-{0}'.format(uuid.uuid4())
    daemon = daemon_factory.new(
        **get_daemon_params(daemon_name, agent_ssl_cert))

    daemon_factory.save(daemon)
    loaded = daemon_factory.load(daemon_name)
    assert 'init.d' == loaded.PROCESS_MANAGEMENT
    assert daemon_name == loaded.name
    assert 'queue' == loaded.queue
    assert '127.0.0.1' == loaded.rest_host
    assert 'user' == loaded.user
    daemon_factory.delete(daemon.name)
    pytest.raises(exceptions.DaemonNotFoundError,
                  daemon_factory.load, daemon.name)


def test_new_no_implementation(daemon_factory):
    pytest.raises(exceptions.DaemonNotImplementedError,
                  daemon_factory.new,
                  process_management='no-impl')


def test_load_non_existing(daemon_factory):
    pytest.raises(exceptions.DaemonNotFoundError,
                  daemon_factory.load,
                  'non_existing_name')


def test_load_all(daemon_factory, agent_ssl_cert):
    def _save_daemon(name):
        daemon_name = 'test-daemon-{0}'.format(uuid.uuid4())
        params = get_daemon_params(daemon_name, agent_ssl_cert).copy()
        params['name'] = name
        daemon = daemon_factory.new(**params)
        daemon_factory.save(daemon)

    if os.path.exists(get_daemon_storage()):
        shutil.rmtree(get_daemon_storage())

    daemons = daemon_factory.load_all()
    assert 0 == len(daemons)
    _save_daemon(utils.internal.generate_agent_name())
    _save_daemon(utils.internal.generate_agent_name())
    _save_daemon(utils.internal.generate_agent_name())

    daemons = daemon_factory.load_all()
    assert 3 == len(daemons)


def test_new_existing_agent(daemon_factory, agent_ssl_cert):
    daemon_name = 'test-daemon-{0}'.format(uuid.uuid4())
    daemon = daemon_factory.new(
        **get_daemon_params(daemon_name, agent_ssl_cert))

    daemon_factory.save(daemon)

    # without no_overwrite, this will overwrite the existing daemon
    daemon = daemon_factory.new(
        **get_daemon_params(daemon_name, agent_ssl_cert))

    pytest.raises(exceptions.DaemonAlreadyExistsError,
                  daemon_factory.new,
                  no_overwrite=True,
                  **get_daemon_params(daemon_name, agent_ssl_cert))


def get_daemon_params(name, ssl_cert):
    return {
        'process_management': 'init.d',
        'name': name,
        'queue': 'queue',
        'rest_host': '127.0.0.1',
        'broker_ip': '127.0.0.1',
        'user': 'user',
        'broker_url': '127.0.0.1',
        'broker_ssl_enabled': True,
        'local_rest_cert_file': ssl_cert.get_local_cert_path(),
    }
