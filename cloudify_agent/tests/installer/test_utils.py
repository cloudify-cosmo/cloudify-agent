from cloudify_agent.api import utils


def test_env_to_file():
    file_path = utils.env_to_file({'key': 'value', 'key2': 'value2'})
    with open(file_path) as f:
        content = f.read()
    assert 'export key=value' in content
    assert 'export key2=value2' in content


def test_env_to_file_nt():
    file_path = utils.env_to_file({'key': 'value', 'key2': 'value2'},
                                  posix=False)
    with open(file_path) as f:
        content = f.read()
    assert 'set key=value' in content
    assert 'set key2=value2' in content


def test_stringify_values():
    env = {
        'key': 'string-value',
        'key2': 5,
        'dict-key': {
            'key3': 10
        }
    }

    stringified = utils.stringify_values(dictionary=env)
    assert stringified['key'] == 'string-value'
    assert stringified['key2'] == '5'
    assert stringified['dict-key']['key3'] == '10'


def test_purge_none_values():
    dictionary = {
        'key': 'value',
        'key2': None
    }

    purged = utils.purge_none_values(dictionary)
    assert purged['key'] == 'value'
    assert 'key2' not in purged
