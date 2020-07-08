import os
import tempfile


def get_agent_dict(env, name='host'):
    node_instances = env.storage.get_node_instances()
    agent_host = [n for n in node_instances if n['name'] == name][0]
    return agent_host['runtime_properties']['cloudify_agent']


def get_storage_directory(_=None):
    return os.path.join(tempfile.gettempdir(), 'cfy-agent-tests-daemons')
