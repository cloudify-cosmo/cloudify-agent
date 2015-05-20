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

import cloudify_agent.api.packager.utils as utils
import cloudify_agent.api.packager.packager as packager
import cloudify_agent.api.packager.codes as codes
from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner

from cloudify_agent.tests import resources
from cloudify_agent.api import defaults

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


def venv(path):
    def real(func):
        @wraps(func)
        def execution_handler(*args, **kwargs):
            try:
                shutil.rmtree(os.path.dirname(path))
            except:
                pass
            utils.make_virtualenv(path)
            func(*args, **kwargs)
            shutil.rmtree(os.path.dirname(path))
        return execution_handler
    return real


class TestBase(testtools.TestCase):

    @classmethod
    def setUpClass(cls):

        cls.logger = setup_logger(
            'test_logger',
            logger_level=logging.INFO)
        cls.runner = LocalCommandRunner(cls.logger)
        cls.packager = packager.Packager(verbose=True)
        cls.config = resources.get_resource(
            os.path.join('packager', 'config_file.yaml'))
        cls.bad_config = resources.get_resource(
            os.path.join('packager', 'bad_config_file.yaml'))
        cls.empty_config = resources.get_resource(
            os.path.join('packager', 'empty_config_file.yaml'))
        cls.base_dir = 'cloudify'
        cls.test_module = 'xmltodict'
        cls.test_download_url = 'https://github.com/cloudify-cosmo/cloudify-agent-packager/archive/master.tar.gz'  # NOQA
        cls.mock_module = resources.get_resource(
            os.path.join('packager', 'mock-module'))
        cls.mock_module_no_includes = resources.get_resource(
            os.path.join('packager', 'mock-module-no-includes'))
        cls.requirements_file_path = resources.get_resource(
            os.path.join('packager', 'requirements.txt'))


class TestUtils(TestBase):

    def test_import_config_file(self):
        outcome = self.packager._import_config(self.config)
        self.assertEquals(type(outcome), dict)
        self.assertIn('distribution', outcome.keys())

    def test_fail_import_config_file(self):
        e = self.assertRaises(
            SystemExit, self.packager._import_config,
            config_file='')
        self.assertEqual(
            codes.errors['could_not_access_config_file'], e.message)

    def test_import_bad_config_file_mapping(self):
        e = self.assertRaises(
            SystemExit, self.packager._import_config,
            config_file=self.bad_config)
        self.assertEqual(codes.errors['invalid_yaml_file'], e.message)

    def test_import_empty_config_file(self):
        e = self.assertRaises(
            SystemExit, self.packager.create,
            config_file=self.empty_config)
        self.assertEqual(
            codes.errors['missing_cloudify_agent_config'], e.message)

    @venv(defaults.VENV_PATH)
    def test_create_virtualenv(self):
        if not os.path.exists('{0}/bin/python'.format(defaults.VENV_PATH)):
            raise Exception('venv not created')

    def test_fail_create_virtualenv_bad_dir(self):
        e = self.assertRaises(
            SystemExit, utils.make_virtualenv, '/' + defaults.VENV_PATH)
        self.assertEqual(
            codes.errors['could_not_create_virtualenv'], e.message)

    def test_fail_create_virtualenv_missing_python(self):
        e = self.assertRaises(
            SystemExit, utils.make_virtualenv, defaults.VENV_PATH,
            '/usr/bin/missing_python')
        self.assertEqual(
            codes.errors['could_not_create_virtualenv'], e.message)

    @venv(defaults.VENV_PATH)
    def test_install_module(self):
        utils.install_module(self.test_module, defaults.VENV_PATH)
        pip_freeze_output = utils.get_installed(defaults.VENV_PATH).lower()
        self.assertIn(self.test_module, pip_freeze_output)

    @venv(defaults.VENV_PATH)
    def test_install_requirements_file(self):
        utils.install_requirements_file(
            self.requirements_file_path, defaults.VENV_PATH)
        pip_freeze_output = utils.get_installed(defaults.VENV_PATH).lower()
        self.assertIn(self.test_module, pip_freeze_output)

    @venv(defaults.VENV_PATH)
    def test_uninstall_module(self):
        utils.install_module(self.test_module, defaults.VENV_PATH)
        utils.uninstall_module(self.test_module, defaults.VENV_PATH)
        pip_freeze_output = utils.get_installed(defaults.VENV_PATH).lower()
        self.assertNotIn(self.test_module, pip_freeze_output)

    @venv(defaults.VENV_PATH)
    def test_uninstall_missing_module(self):
        e = self.assertRaises(
            SystemExit, utils.uninstall_module, 'BLAH!!', defaults.VENV_PATH)
        self.assertEqual(codes.errors['could_not_uninstall_module'], e.message)

    @venv(defaults.VENV_PATH)
    def test_install_nonexisting_module(self):
        e = self.assertRaises(
            SystemExit, utils.install_module, 'BLAH!!', defaults.VENV_PATH)
        self.assertEqual(codes.errors['could_not_install_module'], e.message)

    def test_install_module_nonexisting_venv(self):
        e = self.assertRaises(
            SystemExit, utils.install_module, self.test_module, 'BLAH!!')
        self.assertEqual(codes.errors['virtualenv_not_exists'], e.message)

    @venv(defaults.VENV_PATH)
    def test_check_module_installed(self):
        utils.install_module(self.test_module, defaults.VENV_PATH)
        installed = utils.check_installed(self.test_module, defaults.VENV_PATH)
        self.assertTrue(installed)

    @venv(defaults.VENV_PATH)
    def test_check_module_not_installed(self):
        installed = utils.check_installed(self.test_module, defaults.VENV_PATH)
        self.assertFalse(installed)

    def test_download_file(self):
        utils.download_file(self.test_download_url, 'file')
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
            IOError, utils.download_file, self.test_download_url, 'x/file')
        self.assertIn('No such file or directory', e)

    def test_download_no_permissions(self):
        e = self.assertRaises(
            IOError, utils.download_file, self.test_download_url, '/file')
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

    @venv(defaults.VENV_PATH)
    def test_tar_no_permissions(self):
        e = self.assertRaises(
            SystemExit, utils.tar, defaults.VENV_PATH, '/file')
        self.assertEqual(e.message, codes.errors['failed_to_create_tar'])

    @venv(defaults.VENV_PATH)
    def test_tar_missing_source(self):
        e = self.assertRaises(SystemExit, utils.tar, 'missing', 'file')
        self.assertEqual(e.message, codes.errors['failed_to_create_tar'])
        os.remove('file')


class TestCreate(TestBase):

    def test_create_agent_package(self):
        cli_options = {
            'config_file': self.config,
            'force': True,
            'dryrun': False,
            'no_validate': False
        }
        required_modules = [
            'cloudify-plugins-common',
            'cloudify-rest-client',
            'cloudify-fabric-plugin',
            'cloudify-agent',
            'pyyaml',
            'xmltodict'
        ]
        excluded_modules = [
            'cloudify-diamond-plugin',
            'cloudify-script-plugin'
        ]
        config = self.packager._import_config(self.config)
        self.packager.create(**cli_options)
        if os.path.isdir(defaults.VENV_PATH):
            shutil.rmtree(os.path.dirname(defaults.VENV_PATH))
        os.makedirs(defaults.VENV_PATH)
        self.runner.run('tar -xzvf {0} -C {1} --strip-components=1'.format(
            config['output_tar'], self.base_dir))
        os.remove(config['output_tar'])
        self.assertTrue(os.path.isdir(defaults.VENV_PATH))
        pip_freeze_output = utils.get_installed(
            defaults.VENV_PATH).lower()
        for required_module in required_modules:
            self.assertIn(required_module, pip_freeze_output)
        for excluded_module in excluded_modules:
            self.assertNotIn(excluded_module, pip_freeze_output)
        shutil.rmtree(os.path.dirname(defaults.VENV_PATH))

    def test_dryrun(self):
        cli_options = {
            'config_file': self.config,
            'force': True,
            'dryrun': True,
            'no_validate': False,
        }
        with LogCapture(level=logging.INFO) as l:
            e = self.assertRaises(
                SystemExit, self.packager.create, **cli_options)
            l.check(('cloudify_agent.api.packager.packager',
                     'INFO', 'Dryrun complete'))
        self.assertEqual(codes.notifications['dryrun_complete'], e.message)

    @venv(defaults.VENV_PATH)
    def test_create_agent_package_no_cloudify_agent_configured(self):
        config = self.packager._import_config(self.config)
        del config['cloudify_agent_module']

        e = self.assertRaises(SystemExit, self.packager.create, config, None,
                              force=True)
        self.assertEqual(
            e.message, codes.errors['missing_cloudify_agent_config'])

    @venv(defaults.VENV_PATH)
    def test_create_agent_package_existing_venv_no_force(self):
        e = self.assertRaises(
            SystemExit, self.packager.create, None, self.config)
        self.assertEqual(e.message, codes.errors['virtualenv_already_exists'])

    def test_config_file_not_str(self):
        e = self.assertRaises(
            SystemExit, self.packager.create, None, {'x': 'y'})
        self.assertEqual(e.message, codes.errors['config_file_not_str'])

    def test_config_not_dict(self):
        e = self.assertRaises(
            SystemExit, self.packager.create, 'str', None)
        self.assertEqual(e.message, codes.errors['config_not_dict'])

    @venv(defaults.VENV_PATH)
    def test_create_agent_package_tar_already_exists(self):
        config = self.packager._import_config(self.config)
        shutil.rmtree(defaults.VENV_PATH)
        with open(config['output_tar'], 'w') as a:
            a.write('CONTENT')
        e = self.assertRaises(
            SystemExit, self.packager.create, None, self.config)
        self.assertEqual(e.message, codes.errors['tar_already_exists'])
        os.remove(config['output_tar'])

    @venv(defaults.VENV_PATH)
    def test_generate_includes_file(self):
        """THIS IS CURRENTLY BROKEN.
        Since _generate_includes_file by default outputs to
        os.path.dirname(cloudify_agent.__file__), and the name of the
        package is also cloudify_agent, it imports the directory under
        the cwd rather than the package in the virtualenv.
        requires a solution.

        this does, however, verify that an includes file is generated
        and that the module is added into it.
        """
        utils.install_module(self.mock_module, defaults.VENV_PATH)
        modules = {'plugins': ['cloudify-fabric-plugin']}
        includes_file = self.packager._generate_includes_file(modules)
        includes = imp.load_source('includes_file', includes_file)
        self.assertIn('cloudify-fabric-plugin', includes.included_plugins)

    @venv(defaults.VENV_PATH)
    def test_generate_includes_file_no_previous_includes_file_provided(self):
        """THIS IS CURRENTLY BROKEN.
        Since _generate_includes_file by default outputs to
        os.path.dirname(cloudify_agent.__file__), and the name of the
        package is also cloudify_agent, it imports the directory under
        the cwd rather than the package in the virtualenv.
        requires a solution.

        this does, however, verify that an includes file is generated
        and that the module is added into it.
        """
        utils.install_module(
            self.mock_module_no_includes, defaults.VENV_PATH)
        modules = {'plugins': ['cloudify-fabric-plugin']}
        includes_file = self.packager._generate_includes_file(modules)
        includes = imp.load_source('includes_file', includes_file)
        self.assertIn('cloudify-fabric-plugin', includes.included_plugins)
