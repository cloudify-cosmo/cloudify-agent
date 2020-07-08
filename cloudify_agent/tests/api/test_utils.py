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
    daemon = Daemon(rest_host=['127.0.0.1'], name='name',
                    queue='queue', broker_ip=['127.0.0.1'],
                    local_rest_cert_file=agent_ssl_cert.get_local_cert_path())
    daemon_json = utils.internal.daemon_to_dict(daemon)
    assert daemon_json['rest_host'] == ['127.0.0.1']
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
        rest_host=['127.0.0.1']
    )
    with open(temp) as f:
        rendered = f.read()
        assert 'export REST_HOST="127.0.0.1"' in rendered


def test_resource_to_tempfile():
    temp = utils.resource_to_tempfile(
        resource_path=os.path.join('pm', 'initd', 'initd.conf.template')
    )
    assert os.path.exists(temp)


def test_content_to_tempfile():
    temp = utils.content_to_file(
        content='content'
    )
    with open(temp) as f:
        assert 'content{0}'.format(os.linesep) == f.read()


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
