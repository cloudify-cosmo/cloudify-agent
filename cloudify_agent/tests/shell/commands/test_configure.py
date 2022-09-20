import pytest

from cloudify_agent.tests.shell.commands import run_agent_command


@pytest.mark.only_ci
@pytest.mark.only_posix
def test_configure():
    run_agent_command(
        'cfy-agent configure --disable-requiretty --fix-shebangs')
