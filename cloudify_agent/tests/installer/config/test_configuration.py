from contextlib import contextmanager
import getpass
import os
import platform

from mock import patch

from cloudify import constants
from cloudify_agent.api import utils
from cloudify_agent.installer.config.agent_config import CloudifyAgentConfig
from cloudify_agent.tests.installer.config import mock_context


def test_prepare(agent_ssl_cert):
    expected = _get_distro_package_url()

    _test_prepare(
        agent_ssl_cert,
        agent_config={'local': True},
        expected_values=expected
    )


def test_prepare_secured(agent_ssl_cert):
    expected = _get_distro_package_url(rest_port='443')
    with patch('cloudify.utils.get_manager_rest_service_port',
               return_value=443):
        _test_prepare(
            agent_ssl_cert,
            agent_config={'local': True, 'rest_port': '443'},
            expected_values=expected
        )


def test_prepare_multi_networks(agent_ssl_cert):
    manager_host = '10.0.0.1'
    network_name = 'test_network'
    expected = _get_distro_package_url(manager_host=manager_host)
    expected['rest_host'] = [manager_host]
    expected['broker_ip'] = [manager_host]
    expected['network'] = network_name
    _test_prepare(
        agent_ssl_cert,
        agent_config={
            'local': True,
            'networks': {
                'default': {
                    'manager': manager_host,
                    'brokers': [manager_host],
                },
                network_name: {
                    'manager': manager_host,
                    'brokers': [manager_host],
                },
            },
            'network': network_name
        },
        expected_values=expected,
        context={
            'managers': [{
                'networks': {
                    'default': manager_host,
                    network_name: manager_host
                },
                'ca_cert_content': agent_ssl_cert.DUMMY_CERT,
                'hostname': 'cloudify'
            }],
            'brokers': [{
                'networks': {
                    'default': manager_host,
                    network_name: manager_host
                },
                'ca_cert_content': agent_ssl_cert.DUMMY_CERT,
            }]
        }
    )


def test_connection_params_propagation(agent_ssl_cert):
    with patch('cloudify_agent.installer.config.agent_config.ctx',
               mock_context(
                   agent_ssl_cert,
                   agent_runtime_properties={'extra': {
                       'ssl_cert_path': '/tmp/blabla',
                   }}
               )):
        # Testing that if a connection timeout is passed as an agent runtime
        # property, it would be propagated to the cloudify agent dict
        cloudify_agent = CloudifyAgentConfig()
        cloudify_agent.set_initial_values(True, agent_config={'local': True})
        assert cloudify_agent['ssl_cert_path'] == '/tmp/blabla'


def _get_distro_package_url(rest_port=80, manager_host='127.0.0.1'):
    result = {'rest_port': rest_port}
    base_url = utils.get_manager_file_server_url(manager_host, rest_port)
    agent_package_url = '{0}/packages/agents'.format(base_url)
    if os.name == 'posix':
        distro = platform.dist()[0].lower()
        distro_codename = platform.dist()[2].lower()
        result['distro'] = platform.dist()[0].lower()
        result['distro_codename'] = platform.dist()[2].lower()
        package = '{0}-{1}-agent.tar.gz'.format(distro, distro_codename)
    else:
        package = 'cloudify-windows-agent.exe'
    result['package_url'] = '{0}/{1}'.format(agent_package_url, package)
    result['file_server_url'] = '{proto}://{addr}:{port}/resources'.format(
        proto='https' if rest_port == '443' else 'http',
        addr=manager_host,
        port=rest_port,
    )
    return result


def _test_prepare(agent_ssl_cert, agent_config, expected_values,
                  context=None):
    user = getpass.getuser()
    is_windows = os.name == 'nt'
    basedir = utils.get_agent_basedir(is_windows)
    agent_dir = os.path.join(basedir, 'test_deployment')
    envdir = os.path.join(agent_dir, 'env')
    workdir = os.path.join(agent_dir, 'work')

    # This test needs to be adapted to security settings
    expected = {
        'agent_dir': agent_dir,
        'process_management': {
            'name': 'init.d' if os.name == 'posix' else 'nssm'
        },
        'basedir': basedir,
        'name': 'test_deployment',
        'rest_host': ['127.0.0.1'],
        'broker_ip': ['127.0.0.1'],
        'broker_ssl_cert': agent_ssl_cert.DUMMY_CERT,
        'heartbeat': None,
        'queue': 'test_deployment',
        'envdir': envdir,
        'user': user,
        'local': True,
        'install_method': 'local',
        'disable_requiretty': True,
        'env': {},
        'fabric_env': {},
        'file_server_url': 'https://127.0.0.1:80/resources',
        'max_workers': 5,
        'min_workers': 0,
        'workdir': workdir,
        'broker_ssl_cert_path': os.environ[constants.BROKER_SSL_CERT_PATH],
        'windows': is_windows,
        'system_python': 'python',
        'bypass_maintenance': False,
        'network': 'default',
        'version': utils.get_agent_version(),
        'node_instance_id': 'test_node',
        'log_level': 'info',
        'log_max_bytes': 5242880,
        'log_max_history': 7,
        'rest_ssl_cert': agent_ssl_cert.DUMMY_CERT,
        'tenant': {
            'name': 'default_tenant',
            'rabbitmq_username': 'guest',
            'rabbitmq_password': 'guest',
            'rabbitmq_vhost': '/'
        }
    }
    expected.update(expected_values)

    # port is originally a string because it comes from envvars
    with agent_config_patches(agent_ssl_cert,
                              expected['rest_port'] == '443', context):
        cloudify_agent = CloudifyAgentConfig()
        cloudify_agent.set_initial_values(
            True, agent_config=agent_config)
        cloudify_agent.set_execution_params()
        cloudify_agent.set_default_values()
        cloudify_agent.set_installation_params(None)
        assert expected == cloudify_agent


@contextmanager
def agent_config_patches(agent_ssl_cert, ssl, context):
    context = context or {}
    ctx = mock_context(agent_ssl_cert, **context)
    patches = [
        patch('cloudify_agent.installer.config.agent_config.ctx', ctx),
        patch('cloudify.utils.ctx', mock_context(agent_ssl_cert)),
        patch('cloudify.utils.get_manager_name', return_value='cloudify')
    ]
    if not ssl:
        patches.append(
            patch('cloudify.utils.get_manager_file_server_scheme',
                  return_value='http')
        )
    for p in patches:
        p.start()

    yield

    for p in patches:
        p.stop()
