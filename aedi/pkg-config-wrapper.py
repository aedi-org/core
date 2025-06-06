#!/usr/bin/env python3

#
#    Module to build various libraries and tools for macOS
#    Copyright (C) 2020-2025 Alexey Lysiuk
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import shlex
import subprocess
import sys
from pathlib import Path

_LOG_FILENAME = ''  # 'pkg-config.log'


def _write_log(message: str):
    if not _LOG_FILENAME:
        return

    with open(_LOG_FILENAME, 'a') as log:
        log.write(message)


def _main():
    args = sys.argv[1:]

    cmdline = ' '.join(map(shlex.quote, args))
    _write_log(f'% pkg-config {cmdline}\n')

    bin_path = Path(__file__).parent
    prefix_path = bin_path.parent
    config_path = prefix_path / 'lib/pkgconfig'

    environment = os.environ
    environment['PKG_CONFIG_PATH'] = str(config_path)

    predefined_args = [
        f'{bin_path}/pkgconf',
        f'--define-variable=prefix={prefix_path}',
    ]
    args = predefined_args + args
    result = subprocess.run(args, env=environment, capture_output=True)

    stdout = result.stdout.decode('utf-8')
    stderr = result.stderr.decode('utf-8')

    _write_log('out> ')
    _write_log(stdout if stdout else '\n')
    _write_log('err> ')
    _write_log(stderr if stderr else '\n')

    sys.stdout.write(stdout)
    sys.stderr.write(stderr)

    sys.exit(result.returncode)


if __name__ == '__main__':
    _main()
