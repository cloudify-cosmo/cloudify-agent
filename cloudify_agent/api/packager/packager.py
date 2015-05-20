#########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

import yaml
import json
import shutil
import os
import sys
import imp
import utils
import codes

from cloudify.utils import setup_logger
from cloudify.utils import LocalCommandRunner
from cloudify_agent.api import utils as agent_utils
from cloudify_agent.api import defaults


EXTERNAL_MODULES = [
    'celery==3.1.17'
]

CORE_MODULES_LIST = [
    'cloudify_rest_client',
    'cloudify_plugins_common',
]

CORE_PLUGINS_LIST = [
    'cloudify_script_plugin',
    'cloudify_diamond_plugin',
]

MANDATORY_MODULES = [
    'cloudify_rest_client',
    'cloudify_plugins_common',
]

DEFAULT_CLOUDIFY_AGENT_URL = 'https://github.com/cloudify-cosmo/cloudify-agent/archive/{0}.tar.gz'  # NOQA

logger = setup_logger('cloudify_agent.api.packager.packager')


class Packager():

    def __init__(self, verbose=False, venv=defaults.VENV_PATH):
        self.venv = venv
        self.runner = LocalCommandRunner(logger=logger)
        utils.set_global_verbosity_level(verbose)

    def _import_config(self, config_file=defaults.CONFIG_FILE):
        """returns a configuration object

        :param string config_file: path to config file
        """
        logger.debug('Importing config: {0}...'.format(config_file))
        try:
            with open(config_file, 'r') as c:
                return yaml.safe_load(c.read())
        except IOError as ex:
            logger.error(str(ex))
            logger.error('Cannot access config file')
            sys.exit(codes.errors['could_not_access_config_file'])
        except (yaml.parser.ParserError, yaml.scanner.ScannerError) as ex:
            logger.error(str(ex))
            logger.error('Invalid yaml file')
            sys.exit(codes.errors['invalid_yaml_file'])

    def _make_venv(self, python, force):
        """handles the virtualenv

        removes the virtualenv if required, else, notifies
        that it already exists. If it doesn't exist, it will be
        created.

        :param string venv: path of virtualenv to install in.
        :param string python: python binary path to use.
        :param bool force: whether to force creation or not if it
         already exists.
        """
        if os.path.isdir(self.venv):
            if force:
                logger.info('Removing previous virtualenv...')
                shutil.rmtree(self.venv)
            else:
                logger.error('Virtualenv already exists at {0}. '
                             'You can use the -f flag or delete the '
                             'previous env.'.format(self.venv))
                sys.exit(codes.errors['virtualenv_already_exists'])

        logger.info('Creating virtualenv: {0}'.format(self.venv))
        utils.make_virtualenv(self.venv, python)

    def _handle_output_file(self, destination_tar, force):
        """handles the output tar

        removes the output file if required, else, notifies
        that it already exists.

        :param string destination_tar: destination tar path
        :param bool force: whether to force creation or not if
         it already exists.
        """
        if os.path.isfile(destination_tar) and force:
            logger.info('Removing previous agent package...')
            os.remove(destination_tar)
        if os.path.exists(destination_tar):
                logger.error('Destination tar already exists: {0}'.format(
                    destination_tar))
                sys.exit(codes.errors['tar_already_exists'])

    def _set_defaults(self):
        """sets the default modules dictionary
        """
        logger.debug('Retrieving modules to install...')
        modules = {}
        modules['core_modules'] = {}
        modules['core_plugins'] = {}
        modules['additional_modules'] = []
        modules['additional_plugins'] = {}
        modules['agent'] = ""
        return modules

    def _merge_modules(self, modules, config):
        """merges the default modules with the modules from the config yaml

        :param dict modules: dict containing core and additional
        modules and the cloudify-agent module.
        :param dict config: dict containing the config.
        """
        logger.debug('Merging default modules with config...')

        if 'requirements_file' in config:
            modules['requirements_file'] = config['requirements_file']

        modules['core_modules'].update(config.get('core_modules', {}))
        modules['core_plugins'].update(config.get('core_plugins', {}))

        additional_modules = config.get('additional_modules', [])
        for additional_module in additional_modules:
            modules['additional_modules'].append(additional_module)
        modules['additional_plugins'].update(
            config.get('additional_plugins', {}))

        if 'cloudify_agent_module' in config:
            modules['agent'] = config['cloudify_agent_module']
        elif 'cloudify_agent_version' in config:
            modules['agent'] = defaults.CLOUDIFY_AGENT_URL.format(
                config['cloudify_agent_version'])
        else:
            logger.error('Either `cloudify_agent_module` or '
                         '`cloudify_agent_version` must be specified in the '
                         'yaml configuration file.')
            sys.exit(codes.errors['missing_cloudify_agent_config'])
        return modules

    def _validate(self, modules):
        """validates that all requested modules are actually installed
        within the virtualenv

        :param dict modules: dict containing core and additional
        modules and the cloudify-agent module.
        :param string venv: path of virtualenv to install in.
        """

        failed = []

        logger.info('Validating installation...')
        modules = modules['plugins'] + modules['modules']
        for module_name in modules:
            logger.info('Validating that {0} is installed.'.format(
                module_name))
            if not utils.check_installed(module_name, self.venv):
                logger.error('{0} does not exist in {1}'.format(
                    module_name, self.venv))
                failed.append(module_name)

        if failed:
            logger.error('Validation failed. some of the requested modules '
                         'were not installed.')
            sys.exit(codes.errors['installation_validation_failed'])

    def _install(self, modules, final_set):
        """installs all requested modules

        :param dict modules: dict containing core and additional
        modules and the cloudify-agent module.
        :param string venv: path of virtualenv to install in.
        :param dict final_set: dict to populate with modules.
        """
        installer = ModuleInstaller(modules, self.venv, final_set)
        logger.info('Installing module from requirements file...')
        installer.install_requirements_file()
        logger.info('Installing external modules...')
        installer.install_modules(EXTERNAL_MODULES)
        installer.install_core_modules()
        installer.install_core_plugins()
        logger.info('Installing additional modules...')
        installer.install_modules(modules['additional_modules'])
        installer.install_additional_plugins()
        installer.install_agent()
        return installer.final_set

    def _uninstall_excluded(self, modules):
        """Uninstalls excluded modules.

        Since there is no way to exclude requirements from a module;
        and modules are installed from cloudify-agent's requirements;
        if any modules are chosen to be excluded, they will be uninstalled.

        :param dict modules: dict containing core and additional
        modules and the cloudify-agent module.
        :param string venv: path of virtualenv to install in.
        """
        logger.info('Uninstalling excluded plugins (if any)...')
        for module in CORE_PLUGINS_LIST:
            module_name = _get_module_name(module)
            if modules['core_plugins'].get(module) == 'exclude' and \
                    utils.check_installed(module_name, self.venv):
                logger.info('Uninstalling {0}'.format(module_name))
                utils.uninstall_module(module_name, self.venv)

    def _generate_includes_file(self, modules):
        """generates the included_plugins file for `cloudify-agent` to use

        :param dict modules: dict containing a list of modules and a list
         of plugins. The plugins list will be used to populate the file.
        :param string venv: path of virtualenv to install in.
        """
        logger.debug('Generating includes file...')

        process = self.runner.run('{0} -c "import cloudify_agent;'
                                  ' print cloudify_agent.__file__"'.format(
                                      agent_utils.get_python_path(self.venv)))
        cloudify_agent_module_path = os.path.dirname(process.output)
        output_file = os.path.join(
            cloudify_agent_module_path, defaults.INCLUDES_FILE)

        try:
            current_includes_file = imp.load_source(
                'included_plugins', os.path.join(
                    cloudify_agent_module_path, defaults.INCLUDES_FILE))
            current_plugins_list = current_includes_file.included_plugins
            for plugin in current_plugins_list:
                if plugin not in modules['plugins']:
                    modules['plugins'].append(plugin)
        except IOError:
            logger.debug('Included Plugins file could not be found in agent '
                         'module. A new file will be generated.')
        logger.debug('Writing includes file to: {0}'.format(output_file))
        agent_utils.render_template_to_file(
            defaults.TEMPLATE_FILE, output_file, **modules)
        return output_file

    def create(self, config=None, config_file=None, force=False, dryrun=False,
               no_validate=False):
        """Creates an agent package (tar.gz)

        This will identify the distribution of the host you're running on.
        If it can't identify it for some reason, you'll have to supply a
        `distribution` config object in the config.yaml.

        A virtualenv will be created under
         cloudify/env
        unless configured in the yaml under the `venv` property.
        The order of the modules' installation is as follows:

        cloudify-rest-service
        cloudify-plugins-common
        cloudify-script-plugin
        cloudify-diamond-plugin
        cloudify-agent
        any additional modules specified under `additional_modules` in the yaml
        any additional plugins specified under `additional_plugins` in the yaml

        Once all modules are installed, excluded modules will be uninstalled;
        installation validation will occur; an included_plugins file will be
        generated and a tar.gz file will be created.

        The `output_tar` config object can be specified to determine the path
        to the output file. If omitted, a default path will be given with the
        format `DISTRIBUTION-RELEASE-agent.tar.gz`.
        """

        # this will be updated with installed plugins and modules and used
        # to validate the installation and create the includes file
        final_set = {'modules': [], 'plugins': []}
        # import config
        if config and not isinstance(config, dict):
            logger.error('config must be of type dict, (not {0})'.format(
                type(config)))
            sys.exit(codes.errors['config_not_dict'])
        if config_file and not isinstance(config_file, str):
            logger.error('config_file must be of type str, (not {0})'.format(
                type(config_file)))
            sys.exit(codes.errors['config_file_not_str'])
        if not config:
            config = self._import_config(config_file) if config_file else \
                self._import_config()
            config = {} if not config else config
        try:
            (distro, release) = utils.get_os_props()
            distro = config.get('distribution', distro)
            release = config.get('release', release)
        except Exception as ex:
            logger.error(
                'Distribution info not found in configuration '
                'and could not be retrieved automatically. '
                'please specify the distribution in the yaml. '
                '({0})'.format(ex.message))
            sys.exit(codes.errors['could_not_identify_distribution'])
        python = config.get('python_path', '/usr/bin/python')
        venv = defaults.VENV_PATH
        destination_tar = config.get(
            'output_tar', defaults.OUTPUT_TAR_PATH.format(distro, release))

        logger.debug('Distibution is: {0}'.format(distro))
        logger.debug('Distribution release is: {0}'.format(release))
        logger.debug('Python path is: {0}'.format(python))
        logger.debug('Destination tarfile is: {0}'.format(destination_tar))
        # create modules dict
        modules = self._set_defaults()
        modules = self._merge_modules(modules, config)
        # handle a dryun
        if dryrun:
            utils.set_global_verbosity_level(True)
        logger.debug('Modules and plugins to install: {0}'.format(json.dumps(
            modules, sort_keys=True, indent=4, separators=(',', ': '))))
        if dryrun:
            logger.info('Dryrun complete')
            sys.exit(codes.notifications['dryrun_complete'])
        # create virtualenv
        self._make_venv(python, force)
        # remove output file or alert on existing
        self._handle_output_file(destination_tar, force)
        # install all required modules
        final_set = self._install(modules, final_set)
        # uninstall excluded modules
        self._uninstall_excluded(modules)
        # validate (or not) that all required modules were installed
        if not no_validate:
            self._validate(final_set)
        # generate the includes file
        self._generate_includes_file(final_set)
        # create agent tar
        utils.tar(venv, destination_tar)

        logger.info('The following modules and plugins were installed '
                    'in the agent:\n{0}'.format(
                        utils.get_installed(self.venv)))
        # remove (or not) virtualenv
        if not config.get('keep_virtualenv'):
            logger.info('Removing origin virtualenv {0}'.format(self.venv))
            shutil.rmtree(os.path.dirname(self.venv))
        # duh!
        logger.info('Process complete!')


class ModuleInstaller():
    def __init__(self, modules, venv, final_set):
        self.venv = venv
        self.modules = modules
        self.final_set = final_set

    def install_requirements_file(self):
        if 'requirements_file' in self.modules:
            utils.install_requirements_file(
                self.modules['requirements_file'], self.venv)

    def install_modules(self, modules):
        for module in modules:
            logger.info('Installing module {0}'.format(module))
            utils.install_module(module, self.venv)

    def install_core_modules(self):
        logger.info('Installing core modules...')
        core = self.modules['core_modules']
        # we must run through the CORE_MODULES_LIST so that dependencies are
        # installed in order
        for module in CORE_MODULES_LIST:
            module_name = _get_module_name(module)
            if module in core:
                logger.info('Installing module {0} from {1}.'.format(
                    module_name, core[module]))
                utils.install_module(core[module], self.venv)
                self.final_set['modules'].append(module_name)
            elif module not in core and module in MANDATORY_MODULES:
                logger.info('Module {0} will be installed as a part of '
                            'cloudify-agent '
                            '(This is a mandatory module).'.format(
                                module_name))
            elif module not in core:
                logger.info('Module {0} will be installed as a part of '
                            'cloudify-agent (if applicable).'.format(
                                module_name))

    def install_core_plugins(self):
        logger.info('Installing core plugins...')
        core = self.modules['core_plugins']

        for module in CORE_PLUGINS_LIST:
            module_name = _get_module_name(module)
            if module in core and core[module] == 'exclude':
                logger.info('Module {0} is excluded. '
                            'it will not be a part of the agent.'.format(
                                module_name))
            elif core.get(module):
                logger.info('Installing module {0} from {1}.'.format(
                    module_name, core[module]))
                utils.install_module(core[module], self.venv)
                self.final_set['plugins'].append(module_name)
            elif module not in core:
                logger.info('Module {0} will be installed as a part of '
                            'cloudify-agent (if applicable).'.format(
                                module_name))

    def install_additional_plugins(self):
        logger.info('Installing additional plugins...')
        additional = self.modules['additional_plugins']

        for module, source in additional.items():
            module_name = _get_module_name(module)
            logger.info('Installing module {0} from {1}.'.format(
                module_name, source))
            utils.install_module(source, self.venv)
            self.final_set['plugins'].append(module_name)

    def install_agent(self):
        logger.info('Installing cloudify-agent module from {0}'.format(
            self.modules['agent']))
        utils.install_module(self.modules['agent'], self.venv)
        self.final_set['modules'].append('cloudify-agent')


def _get_module_name(module):
    """returns a module's name
    """
    return module.replace('_', '-')
