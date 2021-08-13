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
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
############

import os
import sys
import time
import logging
import argparse
import traceback
import tempfile
import json
import subprocess
import shutil
import threading
from contextlib import contextmanager

from cloudify import plugin_installer
from cloudify_agent.api import utils
from cloudify_agent.api.factory import DaemonFactory

from cloudify_rest_client.exceptions import (
    UserUnauthorizedError,
    CloudifyClientError
)

from cloudify import constants, dispatch, exceptions, state
from cloudify.context import CloudifyContext
from cloudify.models_states import ExecutionState
from cloudify.logs import setup_agent_logger
from cloudify.state import current_ctx
from cloudify.error_handling import (
    serialize_known_exception,
    deserialize_known_exception
)
from cloudify.amqp_client import (
    AMQPConnection, TaskConsumer, NO_RESPONSE, STOP_AGENT
)
from cloudify.utils import get_manager_name, get_python_path
from cloudify_agent.operations import install_plugins, uninstall_plugins
from cloudify._compat import PY2, parse_version

SYSTEM_DEPLOYMENT = '__system__'
ENV_ENCODING = 'utf-8'  # encoding for env variables
DEFAULT_MAX_WORKERS = 10
CLOUDIFY_DISPATCH = 'CLOUDIFY_DISPATCH'
PREINSTALLED_PLUGINS = [
    'agent',
    'diamond',  # Stub for back compat
    'script',
    'cfy_extensions',
    'default_workflows',
    'worker_installer',
    'cloudify_system_workflows',
    'agent_installer',
]


class LockedFile(object):
    """Like a writable file object, but writes are under a lock.

    Used for logging, so that multiple threads can write to the same logfile
    safely (deployment.log).

    We keep track of the number of users, so that we can close the file
    only when the last one stops writing.
    """
    SETUP_LOGGER_LOCK = threading.Lock()
    LOGFILES = {}

    @classmethod
    def open(cls, fn):
        """Create a new LockedFile, or get a cached one if one for this
        filename already exists.
        """
        with cls.SETUP_LOGGER_LOCK:
            if fn not in cls.LOGFILES:
                if not os.path.exists(os.path.dirname(fn)):
                    os.mkdir(os.path.dirname(fn))
                cls.LOGFILES[fn] = cls(fn)
            rv = cls.LOGFILES[fn]
            rv.users += 1
        return rv

    def __init__(self, filename):
        self._filename = filename
        self._f = None
        self.users = 0
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def write(self, data):
        with self._lock:
            if self._f is None:
                self._f = open(self._filename, 'ab')
            self._f.write(data)
            self._f.flush()

    def close(self):
        with self.SETUP_LOGGER_LOCK:
            self.users -= 1
            if self.users == 0:
                if self._f:
                    self._f.close()
                self.LOGFILES.pop(self._filename)


class TimeoutWrapper(object):
    def __init__(self, ctx, process):
        self.timeout = ctx.timeout
        self.timeout_recoverable = ctx.timeout_recoverable
        self.timeout_encountered = False
        self.process = process
        self.timer = None
        self.logger = logging.getLogger(__name__)

    def _timer_func(self):
        self.timeout_encountered = True
        self.logger.warning("Terminating subprocess; PID=%d...",
                            self.process.pid)
        self.process.terminate()
        for i in range(10):
            if self.process.poll() is not None:
                return
            self.logger.warning("Subprocess still alive; waiting...")
            time.sleep(0.5)
        self.logger.warning("Subprocess still alive; sending KILL signal")
        self.process.kill()
        self.logger.warning("Subprocess killed")

    def __enter__(self):
        if self.timeout:
            self.timer = threading.Timer(self.timeout, self._timer_func)
            self.timer.start()
        return self

    def __exit__(self, *args):
        if self.timer:
            self.timer.cancel()


class CloudifyOperationConsumer(TaskConsumer):
    routing_key = 'operation'
    handler = dispatch.OperationHandler

    def __init__(self, *args, **kwargs):
        self._process_registry = kwargs.pop('registry', None)
        self._plugin_version_cache = {}
        super(CloudifyOperationConsumer, self).__init__(*args, **kwargs)

    def _print_task(self, ctx, action, status=None):
        if ctx.task_type in ['workflow', 'hook']:
            prefix = '{0} {1}'.format(action, ctx.task_type)
            suffix = ''
        elif ctx.type == constants.NODE_INSTANCE:
            prefix = '{0} operation'.format(action)
            suffix = '\n\tNode ID: {0}'.format(ctx.node.id)
        else:
            prefix = ''
            suffix = ''

        if status:
            suffix += '\n\tStatus: {0}'.format(status)

        logger.info(
            '\n\t%(prefix)s on queue `%(queue)s` on tenant `%(tenant)s`:\n'
            '\tTask name: %(name)s\n'
            '\tExecution ID: %(execution_id)s\n'
            '\tWorkflow ID: %(workflow_id)s%(suffix)s\n',
            {'tenant': ctx.tenant_name,
             'prefix': prefix,
             'name': ctx.task_name,
             'queue': ctx.task_target,
             'execution_id': ctx.execution_id,
             'workflow_id': ctx.workflow_id,
             'suffix': suffix})

    @staticmethod
    def _validate_not_cancelled(ctx):
        """
        This method will validate if the current running tasks is cancelled
        or not
        :param handler:
        :param ctx:
        """
        # We need also to handle old tasks still in queue and not picked by
        # the worker so that we can ignore them as the state of the
        # execution is cancelled and ignore pending tasks picked by the
        # worker but still not executed. Morever,we need to handle a case when
        # resume workflow is running while there are some old operations
        # tasks still in the queue which holds an invalid execution token
        # which could raise 401 error
        # Need to use the context associated with the that task
        with state.current_ctx.push(ctx):
            try:
                # Get the status of the current execution so that we can
                # tell if the current running task can be run or not
                current_execution = ctx.get_execution()
                if current_execution:
                    logger.info(
                        'The current status of the execution is {0}'
                        ''.format(current_execution.status)
                    )
                    # If the current execution task is cancelled, that means
                    # some this current task was on the queue when the previous
                    # cancel operation triggered, so we need to ignore running
                    # such tasks from the previous execution which was
                    # cancelled
                    if current_execution.status == ExecutionState.CANCELLED:
                        raise exceptions.ProcessKillCancelled()
                else:
                    raise exceptions.NonRecoverableError(
                        'No execution available'
                    )
            except UserUnauthorizedError:
                # This means that Execution token is no longer valid since
                # there is a new token re-generated because of resume workflow
                raise exceptions.ProcessKillCancelled()

    @contextmanager
    def _update_operation_state(self, ctx, common_version):
        if common_version < parse_version('6.1.0'):
            # plugin's common is old - it does the operation state bookkeeping
            # by itself.
            yield
            return
        store = True
        try:
            op = ctx.get_operation()
        except CloudifyClientError as e:
            if e.status_code == 404:
                op = None
                store = False
            else:
                raise
        if op and op.state == constants.TASK_STARTED:
            # this operation has been started before? that means we're
            # resuming a re-delivered operation
            ctx.resume = True
        if store:
            ctx.update_operation(constants.TASK_STARTED)
        try:
            yield
        finally:
            if store:
                ctx.update_operation(constants.TASK_RESPONSE_SENT)

    def _plugin_common_version(self, executable, env):
        """The cloudify-common version included in the venv at executable.

        Old cloudify-common versions have a slightly different interface,
        so we need to figure out what version each plugin uses.
        """
        if executable not in self._plugin_version_cache:
            get_version_script = (
                'import pkg_resources; '
                'print(pkg_resources.require("cloudify-common")[0].version)'
            )
            try:
                version_output = subprocess.check_output(
                    [executable, '-c', get_version_script], env=env
                ).decode('utf-8')
                version = parse_version(version_output)
            except subprocess.CalledProcessError:
                # we couldn't get it? it's most likely very old
                version = parse_version('0.0.0')
            self._plugin_version_cache[executable] = version
        return self._plugin_version_cache[executable]

    def handle_task(self, full_task):
        task = full_task['cloudify_task']
        raw_ctx = task['kwargs'].pop('__cloudify_context')
        ctx = CloudifyContext(raw_ctx)
        task_args = task.get('args', [])
        task_kwargs = task['kwargs']

        self._print_task(ctx, 'Started handling')
        try:
            self._validate_not_cancelled(ctx)
            rv = self.dispatch_to_subprocess(ctx, task_args, task_kwargs)
            result = {'ok': True, 'result': rv}
            status = 'SUCCESS - result: {0}'.format(result)
        except exceptions.StopAgent:
            result = STOP_AGENT
            status = 'Stopping agent'
        except exceptions.OperationRetry as e:
            result = {'ok': False, 'error': serialize_known_exception(e)}
            status = 'Operation rescheduled'
        except exceptions.ProcessKillCancelled:
            self._print_task(ctx, 'Task kill-cancelled')
            return NO_RESPONSE
        except Exception as e:
            error = serialize_known_exception(e)
            result = {'ok': False, 'error': error}
            status = 'ERROR - result: {0}'.format(result)
            logger.error(
                'ERROR - caught: %r%s',
                e,
                '\n{0}'.format(error['traceback'])
                if error.get('traceback') else ''
            )
        self._print_task(ctx, 'Finished handling', status)
        return result

    def dispatch_to_subprocess(self, ctx, task_args, task_kwargs):
        # inputs.json, output.json and output are written to a temporary
        # directory that only lives during the lifetime of the subprocess
        split = ctx.task_name.split('.')
        dispatch_dir = tempfile.mkdtemp(prefix='task-{0}.{1}-'.format(
            split[0], split[-1]))

        try:
            with open(os.path.join(dispatch_dir, 'input.json'), 'w') as f:
                json.dump({
                    'cloudify_context': ctx._context,
                    'args': task_args,
                    'kwargs': task_kwargs
                }, f)
            if ctx.bypass_maintenance:
                os.environ[constants.BYPASS_MAINTENANCE] = 'True'
            env = self._build_subprocess_env(ctx)

            if self._uses_external_plugin(ctx):
                plugin_dir = self._extract_plugin_dir(ctx)
                if plugin_dir is None:
                    self._install_plugin(ctx)
                    plugin_dir = self._extract_plugin_dir(ctx)
                if plugin_dir is None:
                    raise RuntimeError(
                        'Plugin was not installed: {0}'
                        .format(ctx.plugin.name))
                executable = get_python_path(plugin_dir)
            else:
                executable = sys.executable
            env['PATH'] = os.pathsep.join([
                os.path.dirname(executable), env['PATH']
            ])
            command_args = [executable, '-u', '-m', 'cloudify.dispatch',
                            dispatch_dir]
            common_version = self._plugin_common_version(executable, env)
            with self._update_operation_state(ctx, common_version):
                self.run_subprocess(ctx, command_args,
                                    env=env,
                                    bufsize=1,
                                    close_fds=os.name != 'nt')
            with open(os.path.join(dispatch_dir, 'output.json')) as f:
                dispatch_output = json.load(f)
            return self._handle_subprocess_output(dispatch_output)
        finally:
            shutil.rmtree(dispatch_dir, ignore_errors=True)

    def _handle_subprocess_output(self, dispatch_output):
        if dispatch_output['type'] == 'result':
            return dispatch_output['payload']
        elif dispatch_output['type'] == 'error':
            e = dispatch_output['payload']
            error = deserialize_known_exception(e)
            error.causes.append({
                'message': e['message'],
                'type': e['exception_type'],
                'traceback': e.get('traceback')
            })
            raise error
        else:
            raise exceptions.NonRecoverableError(
                'Unexpected output type: {0}'
                .format(dispatch_output['type']))

    def _build_subprocess_env(self, ctx):
        env = os.environ.copy()

        # marker for code that only gets executed when inside the dispatched
        # subprocess, see usage in the imports section of this module
        env[CLOUDIFY_DISPATCH] = 'true'

        # This is used to support environment variables configurations for
        # central deployment based operations. See workflow_context to
        # understand where this value gets set initially
        # Note that this is received via json, so it is unicode. It must
        # be encoded, because environment variables must be bytes.
        execution_env = ctx.execution_env
        if PY2:
            execution_env = dict((k.encode(ENV_ENCODING),
                                  v.encode(ENV_ENCODING))
                                 for k, v in execution_env.items())
        env.update(execution_env)

        if ctx.bypass_maintenance:
            env[constants.BYPASS_MAINTENANCE] = 'True'
        return env

    def _uses_external_plugin(self, ctx):
        """Whether this operation uses a plugin that is not built-in"""
        if not ctx.plugin.name:
            return False
        if ctx.plugin.name in PREINSTALLED_PLUGINS:
            return False
        return True

    def _extract_plugin_dir(self, ctx):
        return ctx.plugin.prefix

    def _install_plugin(self, ctx):
        with state.current_ctx.push(ctx):
            # source plugins are per-deployment/blueprint, while non-source
            # plugins are expected to be "managed", ie. uploaded to the manager
            if ctx.plugin.source:
                dep_id = ctx.deployment.id
                bp_id = ctx.blueprint.id
            else:
                dep_id = None
                bp_id = None
            plugin_installer.install(
                ctx.plugin._plugin_context,
                deployment_id=dep_id,
                blueprint_id=bp_id)

    def run_subprocess(self, ctx, *subprocess_args, **subprocess_kwargs):
        subprocess_kwargs.setdefault('stderr', subprocess.STDOUT)
        subprocess_kwargs.setdefault('stdout', subprocess.PIPE)
        p = subprocess.Popen(*subprocess_args, **subprocess_kwargs)
        if self._process_registry:
            self._process_registry.register(ctx.execution_id, p)

        with TimeoutWrapper(ctx, p) as timeout_wrapper:
            with self.logfile(ctx) as f:
                while True:
                    line = p.stdout.readline()
                    if line:
                        f.write(line)
                    if p.poll() is not None:
                        break

        cancelled = False
        if self._process_registry:
            cancelled = self._process_registry.is_cancelled(ctx.execution_id)
            self._process_registry.unregister(ctx.execution_id, p)

        if timeout_wrapper.timeout_encountered:
            message = 'Process killed due to timeout of %d seconds' % \
                      timeout_wrapper.timeout
            if p.poll() is None:
                message += ', however it has not stopped yet; please check ' \
                           'process ID {0} manually'.format(p.pid)
            exception_class = exceptions.RecoverableError if \
                timeout_wrapper.timeout_recoverable else \
                exceptions.NonRecoverableError
            raise exception_class(message)

        if p.returncode in (-15, -9):  # SIGTERM, SIGKILL
            if cancelled:
                raise exceptions.ProcessKillCancelled()
            raise exceptions.NonRecoverableError('Process terminated (rc={0})'
                                                 .format(p.returncode))
        if p.returncode != 0:
            raise exceptions.NonRecoverableError(
                'Unhandled exception occurred in operation dispatch (rc={0})'
                .format(p.returncode))

    def logfile(self, ctx):
        try:
            handler_context = ctx.deployment.id
        except AttributeError:
            handler_context = SYSTEM_DEPLOYMENT
        else:
            # an operation may originate from a system wide workflow.
            # in that case, the deployment id will be None
            handler_context = handler_context or SYSTEM_DEPLOYMENT

        log_name = os.path.join(os.environ.get('AGENT_LOG_DIR', ''), 'logs',
                                '{0}.log'.format(handler_context))

        return LockedFile.open(log_name)


class ServiceTaskConsumer(TaskConsumer):
    routing_key = 'service'
    service_tasks = {
        'ping': 'ping_task',
        'cluster-update': 'cluster_update_task',
        'cancel-operation': 'cancel_operation_task',
        'replace-ca-certs': 'replace_ca_certs_task',
        'install-plugin': 'install_plugin_task',
        'uninstall-plugin': 'uninstall_plugin_task',
    }

    def __init__(self, name, *args, **kwargs):
        self.name = name
        self._operation_registry = kwargs.pop('operation_registry')
        super(ServiceTaskConsumer, self).__init__(*args, **kwargs)

    def handle_task(self, full_task):

        task = full_task['service_task']
        task_name = task['task_name']
        kwargs = task['kwargs']

        logger.info(
            'Received `{0}` service task with kwargs: {1}'.format(
                task_name, kwargs))
        task_handler = getattr(self, self.service_tasks[task_name])
        result = task_handler(**kwargs)
        logger.info('Result: {0}'.format(result))
        return result

    def ping_task(self):
        return {'time': time.time()}

    def install_plugin_task(self, plugin, rest_token, tenant,
                            rest_host, target=None, bypass_maintenance=False):

        if target:
            # target was provided, so this is to be installed only on the
            # specified workers, but might have been received by us because
            # it was sent to a fanout exchange.
            # This only matters for mgmtworkers, because agents have no
            # fanout exchanges.
            if get_manager_name() not in target:
                return

        class _EmptyID(object):
            id = None

        class PluginInstallCloudifyContext(object):
            """A CloudifyContext that has just enough data to install plugins
            """
            def __init__(self):
                self.rest_host = rest_host
                self.tenant_name = tenant['name']
                self.rest_token = rest_token
                self.execution_token = None
                self.logger = logging.getLogger('plugin')
                # deployment/blueprint are not defined for force-installs,
                # but the ctx demands they be objects with an .id
                self.deployment = _EmptyID()
                self.blueprint = _EmptyID()
                self.bypass_maintenance = bypass_maintenance

        with current_ctx.push(PluginInstallCloudifyContext()):
            install_plugins([plugin])

    def uninstall_plugin_task(self, plugin, rest_token, tenant,
                              rest_host, target=None,
                              bypass_maintenance=False):

        if target:
            # target was provided, so this is to be installed only on the
            # specified workers, but might have been received by us because
            # it was sent to a fanout exchange.
            # This only matters for mgmtworkers, because agents have no
            # fanout exchanges.
            if get_manager_name() not in target:
                return

        class _EmptyID(object):
            id = None

        class PluginUninstallCloudifyContext(object):
            """A CloudifyContext that has just enough data to uninstall plugins
            """
            def __init__(self):
                self.rest_host = rest_host
                self.tenant_name = tenant['name']
                self.rest_token = rest_token
                self.execution_token = None
                self.logger = logging.getLogger('plugin')
                # deployment/blueprint are not defined for force-installs,
                # but the ctx demands they be objects with an .id
                self.deployment = _EmptyID()
                self.blueprint = _EmptyID()
                self.bypass_maintenance = bypass_maintenance

        with current_ctx.push(PluginUninstallCloudifyContext()):
            uninstall_plugins([plugin])

    def cluster_update_task(self, brokers, broker_ca, managers, manager_ca):
        """Update the running agent with the new cluster.

        When a node is added or removed from the cluster, the agent will
        receive the current cluster nodes in this task. We need to update
        both the current process envvars, the cert files, and all the
        daemon config files.
        """
        self._assert_name('cluster-update')
        factory = DaemonFactory()
        daemon = factory.load(self.name)

        os.environ[constants.REST_HOST_KEY] = \
            u','.join(managers).encode('utf-8')

        with open(daemon.local_rest_cert_file, 'w') as f:
            f.write(manager_ca)
        with open(daemon.broker_ssl_cert_path, 'w') as f:
            f.write(broker_ca)

        daemon.rest_host = managers
        daemon.broker_ip = brokers
        daemon.create_broker_conf()
        daemon.create_config()

        factory.save(daemon)

    def cancel_operation_task(self, execution_id):
        logger.info('Cancelling task %s', execution_id)
        self._operation_registry.cancel(execution_id)

    def replace_ca_certs_task(self, new_manager_ca, new_broker_ca):
        """Update the running agent with new CAs."""
        self._assert_name('replace-ca-certs')
        factory = DaemonFactory()
        daemon = factory.load(self.name)

        if new_broker_ca:
            with open(daemon.broker_ssl_cert_path, 'w') as f:
                f.write(new_broker_ca)
            daemon.create_broker_conf()

        if new_manager_ca:
            with open(daemon.local_rest_cert_file, 'w') as f:
                f.write(new_manager_ca)
            daemon.create_config()

        factory.save(daemon)

    def _assert_name(self, command_name):
        if not self.name:
            raise RuntimeError('{0} sent to agent with no name '
                               'set'.format(command_name))


def _setup_excepthook(daemon_name):
    # Setting a new exception hook to catch any exceptions
    # on agent startup and write them to a file. This file
    # is later read for querying if celery has started successfully.
    current_excepthook = sys.excepthook

    def new_excepthook(exception_type, value, the_traceback):
        # use the storage directory because the work directory might have
        # been created under a different user, in which case we don't have
        # permissions to write to it.
        storage = utils.internal.get_daemon_storage_dir()
        if not os.path.exists(storage):
            os.makedirs(storage)
        error_dump_path = os.path.join(
            utils.internal.get_daemon_storage_dir(),
            '{0}.err'.format(daemon_name))
        with open(error_dump_path, 'w') as f:
            f.write('Type: {0}\n'.format(exception_type))
            f.write('Value: {0}\n'.format(value))
            traceback.print_tb(the_traceback, file=f)
        current_excepthook(exception_type, value, the_traceback)

    sys.excepthook = new_excepthook


class ProcessRegistry(object):
    """A registry for dispatch subprocesses.

    The dispatch TaskHandler uses this to register the subprocesses that
    are running and executing a task, so that they can be cancelled/killed
    from outside.
    """

    def __init__(self):
        self._processes = {}
        self._cancelled = set()

    def register(self, execution_id, process):
        self._processes.setdefault(execution_id, []).append(process)

    def unregister(self, execution_id, process):
        try:
            self._processes[execution_id].remove(process)
        except (KeyError, ValueError):
            pass
        if not self._processes[execution_id] and \
                execution_id in self._cancelled:
            self._cancelled.remove(execution_id)

    def cancel(self, execution_id):
        self._cancelled.add(execution_id)
        threads = [
            threading.Thread(target=self._stop_process, args=(p,))
            for p in self._processes.get(execution_id, [])
        ]
        for thread in threads:
            thread.start()

    def _stop_process(self, process):
        """Stop the process: SIGTERM, and after 5 seconds, SIGKILL

        Note that on windows, both terminate and kill are effectively
        the same operation."""
        process.terminate()
        for i in range(10):
            if process.poll() is not None:
                return
            time.sleep(0.5)
        process.kill()

    def is_cancelled(self, execution_id):
        return execution_id in self._cancelled


def make_amqp_worker(args):
    operation_registry = ProcessRegistry()
    handlers = [
        CloudifyOperationConsumer(args.queue, args.max_workers,
                                  registry=operation_registry),
        ServiceTaskConsumer(args.name, args.queue, args.max_workers,
                            operation_registry=operation_registry),
    ]

    return AMQPConnection(handlers=handlers,
                          name=args.name,
                          connect_timeout=None)


def main():
    global logger

    parser = argparse.ArgumentParser()
    parser.add_argument('--queue')
    parser.add_argument('--max-workers', default=DEFAULT_MAX_WORKERS, type=int)
    parser.add_argument('--name')
    parser.add_argument('--hooks-queue')
    args = parser.parse_args()

    if args.name:
        _setup_excepthook(args.name)
    logger = logging.getLogger('worker.{0}'.format(args.name))
    setup_agent_logger(args.name)

    while True:
        worker = make_amqp_worker(args)
        try:
            worker.consume()
        except Exception:
            logger.exception('Error while reading from rabbitmq')
        time.sleep(1)


if __name__ == '__main__':
    main()
