from contextlib import contextmanager
import getpass
import logging
import os

from mock import patch
import pytest

from cloudify.state import current_ctx
from cloudify import utils as cloudify_utils
from cloudify import constants, exceptions

from cloudify_agent.installer import script
from cloudify_agent.tests.installer.config import mock_context


logger = cloudify_utils.setup_logger(
    'cloudify-agent.tests.installer.script',
    logger_level=logging.DEBUG)


@contextmanager
def set_mock_context(agent_ssl_cert, tmp_path, **override_properties):
    node_properties = {
        'agent_config': {
            'user': getpass.getuser(),
            'install_method': 'init_script',
            'rest_host': 'localhost',
            'windows': os.name == 'nt',
            'basedir': str(tmp_path),
        }
    }
    node_properties['agent_config'].update(**override_properties)
    current_ctx.set(mock_context(agent_ssl_cert, node_id='d',
                                 properties=node_properties))
    yield
    current_ctx.clear()


def _get_install_script(cert, add_ssl_cert=True, extra_agent_params=None):
    input_cloudify_agent = {
        'broker_ip': 'localhost',
        'ssl_cert_path': cert.get_local_cert_path(),
    }
    if extra_agent_params:
        input_cloudify_agent.update(extra_agent_params)
    with patch.dict(os.environ, {constants.MANAGER_NAME: 'cloudify'}):
        script_builder = script._get_script_builder(
            cloudify_agent=input_cloudify_agent
        )
        return script_builder.install_script(add_ssl_cert=add_ssl_cert)


def run_install(commands, windows=False, extra_agent_params=None, cert=None):
    install_script = _get_install_script(cert, windows, extra_agent_params)

    # Remove last line where main function is executed
    install_script = '\n'.join(install_script.split('\n')[:-1])

    if windows:
        install_script_path = os.path.abspath('install_script.ps1')
    else:
        install_script_path = os.path.abspath('install_script.sh')
    with open(install_script_path, 'w') as f:
        f.write(install_script)
        # Inject test commands
        f.write('\n{0}'.format('\n'.join(commands)))

    if windows:
        command_line = 'powershell {0}'.format(install_script_path)
    else:
        os.chmod(install_script_path, 0o755)
        command_line = install_script_path
    runner = cloudify_utils.LocalCommandRunner(logger)
    response = runner.run(command_line)
    return response.std_out


@pytest.mark.only_posix
def test_download_curl(file_server, agent_ssl_cert):
    run_install(['ln -s $(which curl) curl',
                 'PATH=$PWD',
                 'download http://localhost:{0} download.output'
                 .format(file_server.port)],
                cert=agent_ssl_cert)
    assert os.path.isfile('download.output')


@pytest.mark.only_posix
def test_download_wget(file_server, agent_ssl_cert):
    run_install(['ln -s $(which wget) wget',
                 'PATH=$PWD',
                 'download http://localhost:{0} download.output'
                 .format(file_server.port)],
                cert=agent_ssl_cert)
    assert os.path.isfile('download.output')


@pytest.mark.only_posix
def test_download_no_curl_or_wget(file_server, agent_ssl_cert):
    pytest.raises(
        exceptions.CommandExecutionException,
        run_install,
        ['PATH=$PWD',
         'download http://localhost:{0} download.output'
         .format(file_server.port)],
        cert=agent_ssl_cert,
    )


@pytest.mark.only_posix
def test_package_url_implicit(agent_ssl_cert):
    output = run_install(['package_url'], cert=agent_ssl_cert)
    assert '-agent.tar.gz' in output


@pytest.mark.only_posix
def test_package_url_explicit(agent_ssl_cert):
    output = run_install(
        ['package_url'],
        cert=agent_ssl_cert,
        extra_agent_params={
            'distro': 'one',
            'distro_codename': 'two'
        },
    )
    assert 'one-two-agent.tar.gz' in output


@pytest.mark.only_posix
def test_create_custom_env_file(agent_ssl_cert):
    run_install(
        ['create_custom_env_file'],
        cert=agent_ssl_cert,
        extra_agent_params={'env': {'one': 'one'}},
    )
    with open('custom_agent_env.sh') as f:
        assert 'export one="one"' in f.read()


@pytest.mark.only_posix
def test_no_create_custom_env_file(agent_ssl_cert):
    run_install(['create_custom_env_file'], cert=agent_ssl_cert)
    assert not os.path.isfile('custom_agent_env.sh')


@pytest.mark.only_posix
def test_create_ssl_cert(tmp_path, agent_ssl_cert):
    run_install(['add_ssl_cert'], cert=agent_ssl_cert)
    # basedir + node_id
    agent_dir = os.path.join(str(tmp_path), 'd')
    agent_ssl_cert.verify_remote_cert(agent_dir)


def test_add_ssl_func_not_rendered(agent_ssl_cert):
    install_script = _get_install_script(agent_ssl_cert, add_ssl_cert=False)
    assert 'add_ssl_cert' not in install_script


def test_install_is_rendered_by_default(agent_ssl_cert):
    install_script = _get_install_script(agent_ssl_cert)
    assert 'install_agent' in install_script


def test_install_not_rendered_in_provided_mode(tmp_path, agent_ssl_cert):
    with set_mock_context(agent_ssl_cert, tmp_path,
                          install_method='provided'):
        install_script = _get_install_script(agent_ssl_cert)
    assert 'install_agent' not in install_script


@pytest.mark.only_nt
def test_win_create_custom_env_file(agent_ssl_cert):
    run_install(['CreateCustomEnvFile'],
                windows=True,
                cert=agent_ssl_cert,
                extra_agent_params={'env': {'one': 'one'}})
    with open('custom_agent_env.bat') as f:
        assert 'set one="one"' in f.read()


@pytest.mark.only_nt
def test_win_no_create_custom_env_file(agent_ssl_cert):
    run_install(['CreateCustomEnvFile'], windows=True, cert=agent_ssl_cert)
    assert not os.path.isfile('custom_agent_env.bat')


@pytest.mark.only_nt
def test_win_create_ssl_cert(tmp_path, agent_ssl_cert):
    run_install(['AddSSLCert'], windows=True, cert=agent_ssl_cert)
    # basedir + node_id
    agent_dir = os.path.join(str(tmp_path), 'd')
    agent_ssl_cert.verify_remote_cert(agent_dir)
