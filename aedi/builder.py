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

import argparse
import os
import re
import shutil
import subprocess
import typing
from pathlib import Path
from platform import machine

from .packaging.version import Version
from .state import BuildState
from .target import targets
from .target.base import Target
from .utility import (
    OS_VERSION_ARM64,
    OS_VERSION_X86_64,
    CaseInsensitiveDict,
    CommandLineOptions,
    TargetPlatform,
    hardcopy_directories,
)

_MACHO_MAGIC = b'\xcf\xfa\xed\xfe'


class MachOFixer:
    _DESIRED_RPATH = '@loader_path/../lib'

    def __init__(self, state: BuildState):
        self.state = state
        self.is_rpath_set = False

    def run(self):
        self._fix_dir(self.state.install_path)

    @staticmethod
    def _get_path(line: str) -> str:
        match = re.match(r'\s*(name|path) (.+) \(offset \d+\)', line)
        return match.group(2) if match else ''

    def _run_install_name_tool(self, *args):
        args = ('install_name_tool',) + args
        subprocess.run(args, check=True, env=self.state.environment)

    def _update_id_dylib(self, macho: Path, line: str):
        if path := self._get_path(line):
            if not path.startswith('@rpath/'):
                path = os.path.basename(path)
                self._run_install_name_tool('-id', f'@rpath/{path}', macho)

    def _update_load_dylib(self, macho: Path, line: str):
        if path := self._get_path(line):
            for prefix in ('/System/', '/usr/lib/', '@rpath/'):
                if path.startswith(prefix):
                    return

            new_path = os.path.basename(path)
            self._run_install_name_tool('-change', path, f'@rpath/{new_path}', macho)

    def _update_rpath(self, macho: Path, line: str):
        if path := self._get_path(line):
            if path != self._DESIRED_RPATH:
                args = ('-delete_rpath', path) if self.is_rpath_set \
                    else ('-rpath', path, self._DESIRED_RPATH)
                self._run_install_name_tool(*args, macho)

            self.is_rpath_set = True

    def _fix_file(self, path: Path):
        with open(path, 'rb') as f:
            header = f.read(4)

        if header != _MACHO_MAGIC:
            return

        otool_args = ('otool', '-l', path)
        otool_result = subprocess.run(otool_args, check=True, env=self.state.environment, stdout=subprocess.PIPE)
        otool_output = otool_result.stdout.decode('utf-8')

        commands = re.split(r'Load command \d+\n', otool_output)[1:]
        commands = [command.split('\n') for command in commands]

        self.is_rpath_set = False

        for command in commands:
            if len(command) < 3:
                continue

            command_id = command[0].lstrip()
            command_path = command[2]

            if command_id == 'cmd LC_ID_DYLIB':
                self._update_id_dylib(path, command_path)
            elif command_id == 'cmd LC_LOAD_DYLIB':
                self._update_load_dylib(path, command_path)
            elif command_id == 'cmd LC_RPATH':
                self._update_rpath(path, command_path)

        if not self.is_rpath_set:
            args = ('install_name_tool', '-add_rpath', self._DESIRED_RPATH, path)
            subprocess.run(args, check=True, env=self.state.environment)

    def _fix_dir(self, path: Path):
        for name in path.iterdir():
            subpath = path / name

            if name.is_symlink():
                continue
            elif name.is_dir():
                self._fix_dir(subpath)
            else:
                self._fix_file(subpath)


class Builder(object):
    def __init__(self):
        self.argparser = argparse.ArgumentParser()
        self.targets = targets()

    def _create_state(self, args: list):
        self._targets = CaseInsensitiveDict({target.name: target for target in self.targets})

        state = self._state = BuildState()
        state.arguments = arguments = self._parse_arguments(args)
        state.xcode = arguments.xcode
        state.verbose = arguments.verbose

        self._platforms: typing.List[TargetPlatform] = []
        self._populate_platforms(arguments)

        state.platform = self._platforms[0]

        if arguments.temp_path:
            state.temp_path = Path(arguments.temp_path).absolute()

        state.environment['TMPDIR'] = str(state.temp_path) + os.sep
        os.makedirs(state.temp_path, exist_ok=True)

        if arguments.source_path:
            state.source_path = Path(arguments.source_path).absolute()

        if arguments.target:
            self._target = self._targets[arguments.target]
            state.source = state.source_path / self._target.name
            state.external_source = False

            os.makedirs(state.source_path, exist_ok=True)
        else:
            assert arguments.source
            state.source = Path(arguments.source).absolute()
            state.external_source = True
            self._detect_target()

        for target in self._targets.values():
            if target != self._target:
                target.initialize(state)

        del self._targets
        del self.targets

        if arguments.build_path:
            state.build_path = Path(arguments.build_path).absolute()
        else:
            state.build_path = state.root_path / 'build' / self._target.name / ('xcode' if state.xcode else 'make')

        if arguments.output_path:
            state.output_path = Path(arguments.output_path).absolute()
        else:
            state.output_path = state.root_path / 'output'

        self._environment = state.environment

        state.jobs = arguments.jobs and arguments.jobs or self._get_default_job_count()

    def _get_default_job_count(self):
        args = ('sysctl', '-n', 'hw.ncpu')
        result = subprocess.run(args, check=True, env=self._environment, stdout=subprocess.PIPE)
        return result.stdout.decode('ascii').strip()

    def _populate_platforms(self, arguments):
        state = self._state

        def adjust_sdk_path(path: str) -> Path:
            if path:
                return Path(path).absolute()

            sdk_probe_path = state.root_path / 'sdk' / f'MacOSX{os_version}.sdk'
            return sdk_probe_path if sdk_probe_path.exists() else None

        if not arguments.disable_x64:
            os_version = Version(arguments.os_version_x64) if arguments.os_version_x64 else OS_VERSION_X86_64
            assert os_version >= OS_VERSION_X86_64, f'macOS {os_version} is not supported'
            sdk_path = adjust_sdk_path(arguments.sdk_path_x64)
            platform = TargetPlatform('x86_64', 'x86_64-apple-darwin', os_version, sdk_path, state.prefix_path)
            self._platforms.append(platform)

        if not arguments.disable_arm:
            os_version = Version(arguments.os_version_arm) if arguments.os_version_arm else OS_VERSION_ARM64
            assert os_version >= OS_VERSION_ARM64, f'macOS {os_version} is not supported'
            sdk_path = adjust_sdk_path(arguments.sdk_path_arm)
            platform = TargetPlatform('arm64', 'aarch64-apple-darwin', os_version, sdk_path, state.prefix_path)
            self._platforms.append(platform)

        assert len(self._platforms) > 0

        # Put native platform first in the list of platforms
        if self._platforms[0].architecture == machine():
            return

        for platform in self._platforms:
            if platform.architecture == machine():
                native_platform = platform
                self._platforms.remove(platform)
                self._platforms.insert(0, native_platform)
                break

    def run(self, args: list):
        self._create_state(args)

        state = self._state

        # Remove quarantine attribute from entire directory tree ignoring potential errors
        xattr_args = ('/usr/bin/xattr', '-d', '-r', 'com.apple.quarantine', state.root_path)
        subprocess.run(xattr_args, stderr=subprocess.DEVNULL)

        target = self._target
        target.prepare_source(state)

        if target.destination == Target.DESTINATION_DEPS:
            state.install_path = state.deps_path / target.name
        elif target.destination == Target.DESTINATION_OUTPUT:
            state.install_path = state.output_path / target.name

        assert state.install_path
        state.delete_install_directory()

        self._create_prefix_directory()

        if version := state.source_version():
            action = 'Generating' if state.xcode else 'Building'
            print(f'{action} {version}')

        if target.multi_platform and not state.xcode:
            self._build_multiple_platforms()
        else:
            self._build()

        self._sign_outputs()

    def _build(self):
        state = self._state
        state.environment = self._environment.copy()
        state.options = CommandLineOptions()

        target = self._target
        target.configure(state)
        target.build(state)
        target.post_build(state)

        if state.install_path.exists():
            MachOFixer(state).run()

    def _build_multiple_platforms(self):
        target = self._target
        assert target.multi_platform

        state = self._state
        base_build_path = state.build_path
        base_install_path = state.install_path
        install_paths = []

        for platform in self._platforms:
            if platform.architecture in target.unsupported_architectures:
                continue

            state.platform = platform
            state.build_path = base_build_path / ('build_' + platform.architecture)

            if platform.architecture == machine():
                state.native_build_path = state.build_path

            state.install_path = base_build_path / ('install_' + platform.architecture)
            state.delete_install_directory()

            self._build()

            install_paths.append(state.install_path)

        self._merge_install_paths(install_paths, base_install_path)

    @staticmethod
    def _compare_files(paths: typing.Sequence[Path]) -> bool:
        content = None

        for path in paths:
            if not path.exists():
                return False

            with path.open('rb') as f:
                if content:
                    if content != f.read():
                        return False
                else:
                    content = f.read()

        return True

    def _merge_file(self, src: Path, src_sub_paths: typing.Sequence[Path], dst_path: Path):
        if src.is_symlink():
            shutil.copy(src_sub_paths[0], dst_path, follow_symlinks=False)
            return

        with open(src, 'rb') as f:
            header = f.read(8)

        is_executable = header[:4] == _MACHO_MAGIC
        is_library = header == b'!<arch>\n'

        if is_executable or is_library:
            # Merge executable and library files
            dst_file = dst_path / src.name

            args: typing.List[typing.Union[str, Path]] = ['lipo']
            args += src_sub_paths
            args += ['-create', '-output', dst_file]
            subprocess.run(args, check=True, env=self._environment)

            # Apply ad-hoc code signing on executable files outside of application bundles
            if is_executable and '.app/Contents/' not in str(src):
                args = ['codesign', '--sign', '-', dst_file]
                subprocess.run(args, check=True, env=self._environment)
        else:
            if not Builder._compare_files(src_sub_paths):
                print(f'WARNING: Source files for {dst_path / src.name} don\'t match')
            shutil.copy(src_sub_paths[0], dst_path)

    def _merge_missing_files(self, src_paths: typing.Sequence[Path], dst_path: Path):
        shifted_src_paths = [path for path in src_paths]
        last_path_index = len(src_paths) - 1

        for _ in range(last_path_index):
            shifted_src_paths.append(shifted_src_paths[0])
            del shifted_src_paths[0]

            if not shifted_src_paths[0].exists():
                continue

            self._merge_install_paths(shifted_src_paths, dst_path, missing_files_only=True)

    def _merge_install_paths(self, src_paths: typing.Sequence[Path], dst_path: Path, missing_files_only=False):
        if len(src_paths) == 0:
            return

        if not missing_files_only:
            if dst_path.exists():
                shutil.rmtree(dst_path)

        os.makedirs(dst_path, exist_ok=True)

        for src in src_paths[0].iterdir():
            src_sub_paths = [path / src.name for path in src_paths]

            if src.is_dir():
                self._merge_install_paths(src_sub_paths, dst_path / src.name, missing_files_only)
            elif src.name.endswith('.la'):
                # Skip libtool files
                continue
            elif missing_files_only:
                for src_sub_path in src_sub_paths[1:]:
                    if not src_sub_path.exists():
                        shutil.copy(src_sub_paths[0], dst_path)
            else:
                self._merge_file(src, src_sub_paths, dst_path)

        if not missing_files_only:
            self._merge_missing_files(src_paths, dst_path)

    def _sign_outputs(self):
        target = self._target

        if target.destination != Target.DESTINATION_OUTPUT:
            return

        state = self._state

        for output in target.outputs:
            sign_args = ('codesign', '--sign', '-', '--deep', '--force', output)
            subprocess.run(sign_args, check=True, cwd=state.install_path, env=state.environment)

    def _create_prefix_directory(self):
        state = self._state
        prefix_path = state.prefix_path
        core_deps_path = state.core_deps_path
        deps_path = state.deps_path

        os.makedirs(prefix_path, exist_ok=True)

        def list_dir(path: Path):
            return [e for e in path.iterdir() if not str(e).endswith('.gitignore')]

        entries = list_dir(core_deps_path)

        if core_deps_path != deps_path:
            entries += list_dir(deps_path)

        hardcopy_directories(entries, prefix_path)

    def _detect_target(self):
        for name, target in self._targets.items():
            if target.detect(self._state):
                self._target = self._targets[name]
                break

        assert self._target

    def _parse_arguments(self, args: list):
        assert self._targets

        parser = self.argparser

        excl_group = parser.add_mutually_exclusive_group(required=True)
        excl_group.add_argument('--target', choices=self._targets.keys(), help='target to build')
        excl_group.add_argument('--source', metavar='path', help='path to target\'s source code')

        group = parser.add_argument_group('Configuration options')
        group.add_argument('--xcode', action='store_true', help='generate Xcode project instead of build')
        group.add_argument('--os-version-x64', metavar='version', help='macOS deployment version for x86_64')
        group.add_argument('--os-version-arm', metavar='version', help='macOS deployment version for ARM64')
        group.add_argument('--verbose', action='store_true', help='enable verbose build output')
        group.add_argument('--jobs', help='number of parallel compilation jobs')

        excl_group = parser.add_mutually_exclusive_group()
        excl_group.add_argument('--disable-x64', action='store_true', help='disable x86_64 support')
        excl_group.add_argument('--disable-arm', action='store_true', help='disable ARM64 support')

        group = parser.add_argument_group('Paths')
        group.add_argument('--source-path', metavar='path',
                           help='path to store downloaded and checked out source code')
        group.add_argument('--build-path', metavar='path', help='target build path')
        group.add_argument('--output-path', metavar='path', help='output path for main targets')
        group.add_argument('--temp-path', metavar='path', help='path to temporary files directory')
        group.add_argument('--sdk-path-x64', metavar='path', help='path to macOS SDK for x86_64')
        group.add_argument('--sdk-path-arm', metavar='path', help='path to macOS SDK for ARM64')

        return parser.parse_args(args)
