PLUGIN_NAME = 'plugin'
PACKAGE_NAME = 'mock-plugin'
PACKAGE_VERSION = '1.0'


def create_plugin_url(plugin_tar_name, file_server):
    return '{0}/{1}'.format(file_server.url, plugin_tar_name)


def plugin_struct(file_server, source=None, args=None, name=PLUGIN_NAME,
                  executor=None, package_name=PACKAGE_NAME):
    return {
        'source': create_plugin_url(source, file_server) if source else None,
        'install_arguments': args,
        'name': name,
        'package_name': package_name,
        'executor': executor,
        'package_version': '0.0.0'
    }
