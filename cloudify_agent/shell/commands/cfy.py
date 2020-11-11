# #######
# Copyright (c) 2020 Cloudify Platform Ltd. All rights reserved
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
import os
import subprocess
import locale
import codecs

import click

CLICK_CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    token_normalize_func=lambda param: param.lower())


class CommandMixin(object):
    """
    This class mixin helps to set the right locale for system required
    by python 3 for click library where "LC_ALL" & "LANG" are not set and
    in order to avoid the RuntimeError raised by click library which
    prevents invoking cfy commands
    """
    def main(
        self,
        args=None,
        prog_name=None,
        complete_var=None,
        standalone_mode=True,
        **extra
    ):
        # Make sure to set the locale before calling the main method of
        # click command/group that validate if the environment is
        # good for unicode on Python 3 or not.
        self.set_locale_env()
        super(CommandMixin, self).main(
            args=args,
            prog_name=prog_name,
            complete_var=complete_var,
            standalone_mode=standalone_mode,
            **extra
        )

    @staticmethod
    def set_locale_env():
        # inspired by how click library handle unicode for python 3 environment
        # https://github.com/pallets/click/blob/7.1.2/src/click/_unicodefun.py
        try:
            encoding = codecs.lookup(locale.getpreferredencoding()).name
        except Exception:
            encoding = 'ascii'
        if encoding == 'ascii':
            if os.name == "posix":
                try:
                    locales = subprocess.Popen(
                        ["/usr/bin/locale", "-a"], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    ).communicate()[0]
                except OSError:
                    locales = b""

                if isinstance(locales, bytes):
                    locales = locales.decode("ascii", "replace")

                local_to_set = None
                for line in locales.splitlines():
                    locale_env = line.strip()
                    if locale_env.lower() in (
                            "en_us.utf8",
                            "en_us.utf-8",
                            "c.utf8",
                            "c.utf-8"
                    ):
                        local_to_set = locale_env
                    if local_to_set:
                        os.environ['LC_ALL'] = local_to_set
                        os.environ['LANG'] = local_to_set
                        break


class AgentCommand(CommandMixin, click.Command):
    pass


class AgentGroup(CommandMixin, click.Group):
    pass


def group(name=None):
    """
    Use the custom group that handle the Locale for python3
    """
    return click.group(
        name=name,
        context_settings=CLICK_CONTEXT_SETTINGS,
        cls=AgentGroup
    )


def command(*args, **kwargs):
    """
    Use the custom command that handle the Locale for python3
    """
    kwargs.setdefault('cls', AgentCommand)
    return click.command(*args, **kwargs)
