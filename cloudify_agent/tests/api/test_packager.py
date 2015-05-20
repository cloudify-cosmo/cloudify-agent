########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#    * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    * See the License for the specific language governing permissions and
#    * limitations under the License.

__author__ = 'nir0s'

import cloudify_agent.api.packager.utils as utils
import cloudify_agent.api.packager.packager as packager
import cloudify_agent.api.packager.codes as codes
from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner
from requests import ConnectionError

import imp
from testfixtures import LogCapture
from contextlib import closing
import logging
import tarfile
import testtools
import os
import shutil
from functools import wraps


TEST_RESOURCES_DIR = 'cloudify_agent/tests/resources/packager/'
CONFIG_FILE = os.path.join(TEST_RESOURCES_DIR, 'config_file.yaml')
BAD_CONFIG_FILE = os.path.join(TEST_RESOURCES_DIR, 'bad_config_file.yaml')
EMPTY_CONFIG_FILE = os.path.join(TEST_RESOURCES_DIR, 'empty_config_file.yaml')
BASE_DIR = 'cloudify'
TEST_VENV = os.path.join(BASE_DIR, 'env')
TEST_MODULE = 'xmltodict'
TEST_FILE = 'https://github.com/cloudify-cosmo/cloudify-agent-packager/archive/master.tar.gz'  # NOQA
MANAGER = 'https://github.com/cloudify-cosmo/cloudify-manager/archive/master.tar.gz'  # NOQA
MOCK_MODULE = os.path.join(TEST_RESOURCES_DIR, 'mock-module')
MOCK_MODULE_NO_INCLUDES_FILE = os.path.join(
    TEST_RESOURCES_DIR, 'mock-module-no-includes')


def venv(func):
    @wraps(func)
    def execution_handler(*args, **kwargs):
        try:
            shutil.rmtree(TEST_VENV)
        except:
            pass
        utils.make_virtualenv(TEST_VENV)
        func(*args, **kwargs)
        shutil.rmtree(TEST_VENV)
    return execution_handler


class TestUtils(testtools.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.logger = setup_logger(
            'test_logger',
            logger_level=logging.INFO)
        cls.runner = LocalCommandRunner(cls.logger)
        cls.packager = packager.Packager(verbose=True)

    def test_import_config_file(self):
        outcome = self.packager._import_config(CONFIG_FILE)
        self.assertEquals(type(outcome), dict)
        self.assertIn('distribution', outcome.keys())

    def test_fail_import_config_file(self):
        e = self.assertRaises(SystemExit, self.packager._import_config, '')
        self.assertEqual(
            codes.errors['could_not_access_config_file'], e.message)

    def test_import_bad_config_file_mapping(self):
        e = self.assertRaises(
            SystemExit, self.packager._import_config, BAD_CONFIG_FILE)
        self.assertEqual(codes.errors['invalid_yaml_file'], e.message)

    @venv
    def test_create_virtualenv(self):
        if not os.path.exists('{0}/bin/python'.format(TEST_VENV)):
            raise Exception('venv not created')

    def test_fail_create_virtualenv_bad_dir(self):
        e = self.assertRaises(
            SystemExit, utils.make_virtualenv, '/' + TEST_VENV)
        self.assertEqual(
            codes.errors['could_not_create_virtualenv'], e.message)

    def test_fail_create_virtualenv_missing_python(self):
        e = self.assertRaises(
            SystemExit, utils.make_virtualenv, TEST_VENV,
            '/usr/bin/missing_python')
        self.assertEqual(
            codes.errors['could_not_create_virtualenv'], e.message)

    @venv
    def test_install_module(self):
        utils.install_module(TEST_MODULE, TEST_VENV)
        pip_freeze_output = utils.get_installed(TEST_VENV).lower()
        self.assertIn(TEST_MODULE, pip_freeze_output)

    @venv
    def test_install_nonexisting_module(self):
        e = self.assertRaises(
            SystemExit, utils.install_module, 'BLAH!!', TEST_VENV)
        self.assertEqual(codes.errors['could_not_install_module'], e.message)

    def test_install_module_nonexisting_venv(self):
        e = self.assertRaises(
            SystemExit, utils.install_module, TEST_MODULE, 'BLAH!!')
        self.assertEqual(codes.errors['virtualenv_not_exists'], e.message)

    def test_download_file(self):
        utils.download_file(TEST_FILE, 'file')
        if not os.path.isfile('file'):
            raise Exception('file not downloaded')
        os.remove('file')

    def test_download_file_missing(self):
        e = self.assertRaises(
            SystemExit, utils.download_file,
            'http://www.google.com/x.tar.gz', 'file')
        self.assertEqual(
            codes.errors['could_not_download_file'], e.message)

    def test_download_bad_url(self):
        e = self.assertRaises(
            Exception, utils.download_file, 'something', 'file')
        self.assertIn('Invalid URL', e.message)

    def test_download_connection_failed(self):
        e = self.assertRaises(
            ConnectionError, utils.download_file, 'http://something', 'file')
        self.assertIn('Connection aborted', str(e))

    def test_download_missing_path(self):
        e = self.assertRaises(
            IOError, utils.download_file, TEST_FILE, 'x/file')
        self.assertIn('No such file or directory', e)

    def test_download_no_permissions(self):
        e = self.assertRaises(IOError, utils.download_file, TEST_FILE, '/file')
        self.assertIn('Permission denied', e)

    def test_tar(self):
        os.makedirs('dir')
        with open('dir/content.file', 'w') as f:
            f.write('CONTENT')
        utils.tar('dir', 'tar.file')
        shutil.rmtree('dir')
        self.assertTrue(tarfile.is_tarfile('tar.file'))
        with closing(tarfile.open('tar.file', 'r:gz')) as tar:
            members = tar.getnames()
            self.assertIn('dir/content.file', members)
        os.remove('tar.file')

    @venv
    def test_tar_no_permissions(self):
        e = self.assertRaises(SystemExit, utils.tar, TEST_VENV, '/file')
        self.assertEqual(e.message, codes.errors['failed_to_create_tar'])

    @venv
    def test_tar_missing_source(self):
        e = self.assertRaises(SystemExit, utils.tar, 'missing', 'file')
        self.assertEqual(e.message, codes.errors['failed_to_create_tar'])
        os.remove('file')


class TestCreate(testtools.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.logger = setup_logger(
            'test_logger',
            logger_level=logging.INFO)
        cls.runner = LocalCommandRunner(cls.logger)
        cls.packager = packager.Packager(verbose=True, venv=TEST_VENV)
    # def test_create_agent_package(self):
    #     cli_options = {
    #         '--config': CONFIG_FILE,
    #         '--force': True,
    #         '--dryrun': False,
    #         '--no-validation': False,
    #         '--verbose': True
    #     }
    #     required_modules = [
    #         'cloudify-plugins-common',
    #         'cloudify-rest-client',
    #         'cloudify-fabric-plugin',
    #         'cloudify-agent',
    #         'pyyaml',
    #         'xmltodict'
    #     ]
    #     excluded_modules = [
    #         'cloudify-diamond-plugin',
    #         'cloudify-script-plugin'
    #     ]
    #     config = ap._import_config(CONFIG_FILE)
    #     cli._run(cli_options)
    #     if os.path.isdir(TEST_VENV):
    #         shutil.rmtree(TEST_VENV)
    #     os.makedirs(TEST_VENV)
    #     utils.run('tar -xzvf {0} -C {1} --strip-components=1'.format(
    #         config['output_tar'], BASE_DIR))
    #     os.remove(config['output_tar'])
    #     self.assertTrue(os.path.isdir(TEST_VENV))
    #     pip_freeze_output = utils.get_installed(
    #         TEST_VENV).lower()
    #     for required_module in required_modules:
    #         self.assertIn(required_module, pip_freeze_output)
    #     for excluded_module in excluded_modules:
    #         self.assertNotIn(excluded_module, pip_freeze_output)
    #     shutil.rmtree(TEST_VENV)

    # def test_dryrun(self):
    #     cli_options = {
    #         '--config': CONFIG_FILE,
    #         '--force': True,
    #         '--dryrun': True,
    #         '--no-validation': False,
    #         '--verbose': True
    #     }
    #     with LogCapture(level=logging.INFO) as l:
    #         e = self.assertRaises(SystemExit, cli._run, cli_options)
    #         l.check(('user', 'INFO', 'Creating virtualenv: {0}'.format(
    #             TEST_VENV)),
    #             ('user', 'INFO', 'Dryrun complete'))
    #     self.assertEqual(codes.notifications['dryrun_complete'], e.message)

    @venv
    def test_create_agent_package_no_cloudify_agent_configured(self):
        config = self.packager._import_config(CONFIG_FILE)
        del config['cloudify_agent_module']

        e = self.assertRaises(SystemExit, self.packager.create, config, None,
                              force=True)
        self.assertEqual(
            e.message, codes.errors['missing_cloudify_agent_config'])

    @venv
    def test_create_agent_package_existing_venv_no_force(self):
        e = self.assertRaises(
            SystemExit, self.packager.create, None, CONFIG_FILE)
        self.assertEqual(e.message, codes.errors['virtualenv_already_exists'])

    @venv
    def test_create_agent_package_tar_already_exists(self):
        config = self.packager._import_config(CONFIG_FILE)
        shutil.rmtree(TEST_VENV)
        with open(config['output_tar'], 'w') as a:
            a.write('CONTENT')
        e = self.assertRaises(
            SystemExit, self.packager.create, None, CONFIG_FILE)
        self.assertEqual(e.message, codes.errors['tar_already_exists'])
        os.remove(config['output_tar'])

    @venv
    def test_generate_includes_file(self):
        utils.install_module(MOCK_MODULE, TEST_VENV)
        modules = {'plugins': ['cloudify-fabric-plugin']}
        includes_file = self.packager._generate_includes_file(modules)
        includes = imp.load_source('includes_file', includes_file)
        self.assertIn('cloudify-fabric-plugin', includes.included_plugins)
        self.assertIn('cloudify-puppet-plugin', includes.included_plugins)

    @venv
    def test_generate_includes_file_no_previous_includes_file_provided(self):
        utils.install_module(MOCK_MODULE_NO_INCLUDES_FILE, TEST_VENV)
        modules = {'plugins': ['cloudify-fabric-plugin']}
        includes_file = self.packager._generate_includes_file(modules)
        includes = imp.load_source('includes_file', includes_file)
        self.assertIn('cloudify-fabric-plugin', includes.included_plugins)
