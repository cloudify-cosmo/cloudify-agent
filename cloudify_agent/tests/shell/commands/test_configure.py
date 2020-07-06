from cloudify_agent.tests.api.pm import only_ci, only_os
from cloudify_agent.tests.shell.commands import run_agent_command


@only_ci
@only_os('posix')
def test_configure():
    run_agent_command(
        'cfy-agent configure --disable-requiretty --relocated-env')
