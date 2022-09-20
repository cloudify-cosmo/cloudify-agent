from mock import patch

from cloudify_agent.tests.resources import get_resource

from cloudify.workflows import local

from cloudify_agent.installer import AgentInstaller


# These tests validate that when using older blueprints (3.2), the new
# cloudify_agent operations are invoked

def test_install_agent():
    _test_install_agent('test-install-agent-blueprint.yaml')


def test_install_agent_windows():
    _test_install_agent('test-install-agent-blueprint-windows.yaml')


def test_create_process_management_options():
    def _test_param(value, expected=None):
        installer = AgentInstaller({
            'process_management': {
                'name': 'nssm',
                'param': value,
            }
        })
        result = installer._create_process_management_options()
        assert result == "--param={0}".format(expected or value)

    _test_param('value1')
    _test_param('value2with$sign', "'value2with$sign'")


# Patch _validate_node, to allow installing agent in local mode
@patch('cloudify.workflows.local._validate_node')
@patch('cloudify_agent.installer.operations.start')
@patch('cloudify_agent.installer.operations.create')
def _test_install_agent(blueprint,
                        create_mock,
                        start_mock, *_):
    blueprint_path = get_resource(
        'blueprints/install-agent/{0}'.format(blueprint)
    )
    env = local.init_env(blueprint_path)
    env.execute('install')
    create_mock.assert_called_once()
    start_mock.assert_called_once()
