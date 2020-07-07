import getpass
import os

from mock import patch

from cloudify import amqp_client
from cloudify.error_handling import deserialize_known_exception
from cloudify.utils import LocalCommandRunner

from cloudify_agent.api import utils
from cloudify_agent.api.factory import DaemonFactory
from cloudify_agent.api.pm.detach import DetachedDaemon
from cloudify_agent.api.pm.initd import InitDDaemon
from cloudify_agent.api.pm.nssm import NonSuckingServiceManagerDaemon

from cloudify_agent.tests import get_storage_directory
from cloudify_agent.tests import resources
from cloudify_agent.tests import utils as test_utils


BUILT_IN_TASKS = [
    'cloudify.dispatch.dispatch',
    'cluster-update'
]
PLUGIN_NAME = 'plugin'


@patch('cloudify_agent.api.utils.internal.get_storage_directory',
       get_storage_directory)
class BaseDaemon:
    def __init__(self, tmp_path, logger, ssl_cert):
        self.daemons = []
        self.temp_folder = str(tmp_path)
        self.username = getpass.getuser()
        self.logger = logger
        self.rest_cert_path = ssl_cert.get_local_cert_path()
        self.factory = DaemonFactory()
        self.runner = LocalCommandRunner(logger=logger)

    @property
    def daemon_cls(self):
        raise NotImplementedError('Must be implemented by sub-class')

    def create_daemon(self, **attributes):
        name = utils.internal.generate_agent_name()

        params = {
            'rest_host': ['127.0.0.1'],
            'broker_ip': ['127.0.0.1'],
            'user': self.username,
            'workdir': self.temp_folder,
            'logger': self.logger,
            'name': name,
            'queue': '{0}-queue'.format(name),
            'local_rest_cert_file': self.rest_cert_path,
            'broker_ssl_enabled': False,  # No SSL on the CI machines
        }
        params.update(attributes)

        daemon = self.daemon_cls(**params)
        self.factory.save(daemon)
        self.daemons.append(daemon)
        return daemon

    @staticmethod
    def plugin_struct(plugin_name='mock-plugin'):
        return {
            'source': os.path.join(resources.get_resource('plugins'),
                                   plugin_name),
            'name': PLUGIN_NAME
        }

    def send_task(self,
                  task_name,
                  queue,
                  deployment_id=None,
                  args=None,
                  kwargs=None,
                  timeout=10,
                  execution_env=None):
        cloudify_context = test_utils.op_context(task_name,
                                                 task_target=queue,
                                                 plugin_name=PLUGIN_NAME,
                                                 execution_env=execution_env,
                                                 deployment_id=deployment_id)
        kwargs = kwargs or {}
        kwargs['__cloudify_context'] = cloudify_context
        handler = amqp_client.BlockingRequestResponseHandler(queue)
        client = amqp_client.get_client()
        client.add_handler(handler)
        with client:
            task = {'cloudify_task': {'kwargs': kwargs}}
            result = handler.publish(task, routing_key='operation',
                                     timeout=timeout)
        error = result.get('error')
        if error:
            raise deserialize_known_exception(error)
        else:
            return result.get('result')


class TestDetachedDaemon(BaseDaemon):
    @property
    def daemon_cls(self):
        return DetachedDaemon


class TestInitdDaemon(BaseDaemon):
    @property
    def daemon_cls(self):
        return InitDDaemon


class TestNSSMDaemon(BaseDaemon):
    @property
    def daemon_cls(self):
        return NonSuckingServiceManagerDaemon
