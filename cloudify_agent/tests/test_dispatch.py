import json
import mock
import pytest

from cloudify import exceptions, constants
from cloudify.context import CloudifyContext
from cloudify_agent import worker


def _make_mock_popen():
    popen = mock.Mock()
    popen.stdout = mock.Mock()
    popen.stdout.readline.side_effect = ['']
    popen.returncode = 0
    return mock.Mock(return_value=popen)


@mock.patch('subprocess.Popen', side_effect=_make_mock_popen())
def test_full_dispatch(mock_popen, tmpdir):
    """Check that the main subprocess method works at all"""
    consumer = worker.CloudifyOperationConsumer(None)
    with open(tmpdir / 'output.json', 'w') as f:
        json.dump({'type': 'result', 'payload': 42}, f)
    with mock.patch('tempfile.mkdtemp', return_value=tmpdir):
        result = consumer.dispatch_to_subprocess(CloudifyContext({
            'task_name': 'plugin.task',
        }), (), {})
    assert result == 42


def test_handle_result():
    consumer = worker.CloudifyOperationConsumer(None)
    assert consumer._handle_subprocess_output(
        {'type': 'result', 'payload': 42}
    ) == 42


def test_handle_result_unknown_type():
    consumer = worker.CloudifyOperationConsumer(None)
    with pytest.raises(exceptions.NonRecoverableError):
        consumer._handle_subprocess_output({'type': 'unknown'})


def test_handle_result_deserialize_exception():
    consumer = worker.CloudifyOperationConsumer(None)
    with pytest.raises(exceptions.RecoverableError, match='foobar'):
        consumer._handle_subprocess_output({
            'type': 'error',
            'payload': {
                'known_exception_type': 'RecoverableError',
                'exception_type': 'RecoverableError',
                'message': 'foobar',
                'known_exception_type_args': [],
                'known_exception_type_kwargs': {},
                'append_message': False
            }
        })


def test_uses_external_plugin():
    consumer = worker.CloudifyOperationConsumer(None)
    assert consumer._uses_external_plugin(CloudifyContext(
        {'plugin': {'name': 'plugin'}}))
    for builtin_plugin in worker.PREINSTALLED_PLUGINS:
        assert not consumer._uses_external_plugin(CloudifyContext(
            {'plugin': {'name': builtin_plugin}}))


def test_subprocess_env():
    consumer = worker.CloudifyOperationConsumer(None)
    env = consumer._build_subprocess_env(CloudifyContext({}))
    assert worker.CLOUDIFY_DISPATCH in env
    assert constants.BYPASS_MAINTENANCE not in env
    bypass_env = consumer._build_subprocess_env(
        CloudifyContext({'bypass_maintenance': True}))
    assert constants.BYPASS_MAINTENANCE in bypass_env
