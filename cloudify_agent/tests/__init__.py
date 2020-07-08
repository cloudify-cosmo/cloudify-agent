import os
import logging
import tempfile
import getpass
import shutil

from cloudify import constants, mocks
from cloudify.state import current_ctx
from cloudify.utils import setup_logger

try:
    win_error = WindowsError
except NameError:
    win_error = None


def get_agent_dict(env, name='host'):
    node_instances = env.storage.get_node_instances()
    agent_host = [n for n in node_instances if n['name'] == name][0]
    return agent_host['runtime_properties']['cloudify_agent']


def get_storage_directory(_=None):
    return os.path.join(tempfile.gettempdir(), 'cfy-agent-tests-daemons')


class BaseTest(object):
    def setUp(self):
        super(BaseTest, self).setUp()
        self.temp_folder = tempfile.mkdtemp(prefix='cfy-agent-tests-')

        # change levels to 'DEBUG' to troubleshoot.
        self.logger = setup_logger(
            'cloudify-agent.tests',
            logger_level=logging.INFO)
        from cloudify_agent.api import utils
        utils.logger.setLevel(logging.INFO)

        self.curr_dir = os.getcwd()

        def clean_folder(folder_name):
            try:
                shutil.rmtree(folder_name)
            except win_error:
                # no hard feeling if file is locked.
                pass

        def clean_storage_dir():
            if os.path.exists(get_storage_directory()):
                clean_folder(get_storage_directory())

        self.addCleanup(clean_folder, folder_name=self.temp_folder)
        self.addCleanup(clean_storage_dir)
        os.chdir(self.temp_folder)
        self.addCleanup(lambda: os.chdir(self.curr_dir))

        self.username = getpass.getuser()
        self.logger.info('Working directory: {0}'.format(self.temp_folder))

        self.mock_ctx_with_tenant()

    def mock_ctx_with_tenant(self):
        self.original_ctx = current_ctx
        current_ctx.set(
            mocks.MockCloudifyContext(tenant={'name': 'default_tenant'}))
        self.addCleanup(self._restore_ctx)

    def _restore_ctx(self):
        current_ctx.set(self.original_ctx)
