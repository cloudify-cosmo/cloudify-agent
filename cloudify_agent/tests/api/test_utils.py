import os

from cloudify.utils import setup_logger

import cloudify_agent
from cloudify_agent.api import utils
from cloudify_agent.api import defaults
from cloudify_agent.api.pm.base import Daemon


logger = setup_logger('cloudify_agent.tests.api.test_utils')


def test_get_absolute_resource_path():
    full_path = utils.get_absolute_resource_path(
        os.path.join('pm', 'nssm', 'nssm.exe'))
    expected = os.path.join(
        os.path.dirname(cloudify_agent.__file__),
        'resources',
        'pm',
        'nssm',
        'nssm.exe')
    assert expected == full_path


def test_daemon_to_dict(agent_ssl_cert):
    daemon = Daemon(
        rest_host=['127.0.0.1'],
        name='name',
        queue='queue',
        broker_ip=['127.0.0.1'],
        local_rest_cert_file=agent_ssl_cert.local_cert_path(),
        broker_ssl_cert_path=agent_ssl_cert.local_cert_path(),
    )
    daemon_json = daemon.as_dict()
    assert daemon_json['broker_ip'] == ['127.0.0.1']
    assert daemon_json['name'] == 'name'
    assert daemon_json['queue'] == 'queue'


def test_get_resource():
    resource = utils.get_resource(os.path.join(
        'pm',
        'initd',
        'initd.conf.template'
    ))
    assert resource is not None


def test_rendered_template_to_file():
    temp = utils.render_template_to_file(
        template_path=os.path.join('pm', 'initd', 'initd.conf.template'),
        name='agent1'
    )
    with open(temp) as f:
        rendered = f.read()
        assert 'export AGENT_NAME="agent1' in rendered


def test_resource_to_tempfile():
    temp = utils.resource_to_tempfile(
        resource_path=os.path.join('pm', 'initd', 'initd.conf.template')
    )
    assert os.path.exists(temp)


def test_content_to_tempfile():
    temp = utils.content_to_file(
        content='content'
    )
    # Because otherwise py3 will behave differently due to universal newlines
    expected = b'content' + os.linesep.encode('ascii')
    with open(temp, 'rb') as f:
        assert expected == f.read()


def test_generate_agent_name():
    name = utils.internal.generate_agent_name()
    assert defaults.CLOUDIFY_AGENT_PREFIX in name


def test_get_broker_url():
    config = dict(broker_ip='10.50.50.3',
                  broker_user='us#er',
                  broker_pass='pa$$word',
                  broker_vhost='vh0$t',
                  broker_ssl_enabled=True)
    assert 'amqp://us%23er:pa%24%24word@10.50.50.3:5671/vh0$t' == \
        utils.internal.get_broker_url(config)
