from mock import patch

from cloudify_agent.tests.resources import get_resource

from cloudify.workflows import local


# These tests validate that when using older blueprints (3.2), the new
# cloudify_agent operations are invoked

def test_install_agent():
    _test_install_agent('test-install-agent-blueprint.yaml')


def test_install_agent_windows():
    _test_install_agent('test-install-agent-blueprint-windows.yaml')


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
