import os
import sys

from cloudify import ctx
from cloudify.state import ctx_parameters as inputs
from cloudify import exceptions
from cloudify_agent import VIRTUALENV


def get_reboot_path():
    plugins_dir = os.path.join(VIRTUALENV, 'plugins')
    for entry in os.listdir(plugins_dir):
        plugin_dir = os.path.join(plugins_dir, entry)
        if (os.path.isdir(plugin_dir) and
                entry.startswith('cloudify-openstack-plugin')):
            openstack_plugin_env_dir = plugin_dir
            break
    else:
        raise exceptions.NonRecoverableError('Could not find openstack plugin')
    site_packages = os.path.join(
        openstack_plugin_env_dir,
        'lib',
        'python{0}.{1}'.format(sys.version_info[0],
                               sys.version_info[1]),
        'site-packages')
    return os.path.join(site_packages, 'nova_plugin', 'reboot.py')


def copy_reboot():
    target_path = get_reboot_path()
    if not os.path.exists(target_path):
        ctx.download_resource('scripts/reboot.py', target_path=target_path)


def delete_reboot():
    target_path = get_reboot_path()
    if os.path.exists(target_path):
        os.remove(target_path)


def main():
    globals()[inputs.operation]()

if __name__ == '__main__':
    main()
