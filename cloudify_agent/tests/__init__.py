import random


def get_agent_dict(env, name='host'):
    node_instances = env.storage.get_node_instances()
    agent_host = [n for n in node_instances if n['name'] == name][0]
    return agent_host['runtime_properties']['cloudify_agent']


def random_id(with_prefix=True):
    _id = 'cfy-agent-' if with_prefix else ''
    # To avoid hitting crontab line length issues we avoid uuids
    _id += str(random.randint(1, 1000000))
    return _id
