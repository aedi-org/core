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
import platform
import subprocess

from .. import utility
from ..state import BuildState
from . import base


class CMakeTarget(base.CMakeTarget):
    def __init__(self):
        super().__init__('cmake')

    def prepare_source(self, state: BuildState):
        state.download_source(
            'https://github.com/Kitware/CMake/releases/download/v3.31.7/cmake-3.31.7.tar.gz',
            'a6d2eb1ebeb99130dfe63ef5a340c3fdb11431cce3d7ca148524c125924cea68')

    def configure(self, state: BuildState):
        # Bootstrap native CMake binary
        boostrap_path = state.native_build_path / '__bootstrap__'
        boostrap_cmk_path = boostrap_path / 'Bootstrap.cmk'
        boostrap_cmake = boostrap_cmk_path / 'cmake'

        if state.architecture() == platform.machine():
            if not boostrap_cmake.exists():
                os.makedirs(boostrap_path, exist_ok=True)

                args = (state.source / 'configure', '--parallel=' + state.jobs)
                subprocess.run(args, check=True, cwd=boostrap_path, env=state.environment)

                assert boostrap_cmake.exists()

        env = state.environment
        env['PATH'] = os.pathsep.join([str(boostrap_cmk_path), env['PATH']])

        super().configure(state)

    def post_build(self, state: BuildState):
        self.install(state)


class GmakeTarget(base.ConfigureMakeDependencyTarget):
    def __init__(self):
        super().__init__('gmake')

    def prepare_source(self, state: BuildState):
        state.download_source(
            'https://ftpmirror.gnu.org/make/make-4.4.1.tar.lz',
            '8814ba072182b605d156d7589c19a43b89fc58ea479b9355146160946f8cf6e9')

    def detect(self, state: BuildState) -> bool:
        return state.has_source_file('doc/make.1')

    def post_build(self, state: BuildState):
        self.copy_to_bin(state, 'make', self.name)


class MesonTarget(base.BuildTarget):
    def __init__(self):
        super().__init__('meson')
        self.multi_platform = False

    def prepare_source(self, state: BuildState):
        state.download_source(
            'https://github.com/mesonbuild/meson/releases/download/1.8.4/meson-1.8.4.tar.gz',
            '5fabf143f58e6636c8ff41ae489bbd5d5d86f881f0a1ef1726cfaf703116e071')

    def detect(self, state: BuildState) -> bool:
        return state.has_source_file('meson.py')

    def post_build(self, state: BuildState):
        install_path = state.install_path / 'bin'
        install_path.mkdir(parents=True)

        source_path = state.source
        utility.hardcopy_directory(source_path / 'mesonbuild', state.install_path / 'lib/python/mesonbuild')
        utility.hardcopy(source_path / 'meson.py', install_path / 'meson')


class NasmTarget(base.ConfigureMakeDependencyTarget):
    def __init__(self):
        super().__init__('nasm')

    def prepare_source(self, state: BuildState):
        state.download_source(
            'https://www.nasm.us/pub/nasm/releasebuilds/2.16.03/nasm-2.16.03.tar.xz',
            '1412a1c760bbd05db026b6c0d1657affd6631cd0a63cddb6f73cc6d4aa616148',
            patches='nasm-deterministic-date')

    def detect(self, state: BuildState) -> bool:
        return state.has_source_file('nasm.txt')


class NinjaTarget(base.CMakeStaticDependencyTarget):
    def __init__(self):
        super().__init__('ninja')

    def prepare_source(self, state: BuildState):
        state.download_source(
            'https://github.com/ninja-build/ninja/archive/refs/tags/v1.12.1.tar.gz',
            '821bdff48a3f683bc4bb3b6f0b5fe7b2d647cf65d52aeb63328c91a6c6df285a')


class PkgconfTarget(base.ConfigureMakeStaticDependencyTarget):
    def __init__(self):
        super().__init__('pkgconf')

    def prepare_source(self, state: BuildState):
        state.download_source(
            'https://distfiles.ariadne.space/pkgconf/pkgconf-2.5.1.tar.xz',
            'cd05c9589b9f86ecf044c10a2269822bc9eb001eced2582cfffd658b0a50c243')

    def detect(self, state: BuildState) -> bool:
        return state.has_source_file('libpkgconf/libpkgconf.h')

    def post_build(self, state: BuildState):
        self.copy_to_bin(state)


class YasmTarget(base.CMakeDependencyTarget):
    def __init__(self):
        super().__init__('yasm')

        # CMake allows to build yasm shared library, but cross-compilation is not supported
        self.multi_platform = False

    def prepare_source(self, state: BuildState):
        state.download_source(
            'https://www.tortall.net/projects/yasm/releases/yasm-1.3.0.tar.gz',
            '3dce6601b495f5b3d45b59f7d2492a340ee7e84b5beca17e48f862502bd5603f')

        # Set deterministic build date of the corresponding tagged commit
        state.set_build_datetime(2014, 8, 10, 23, 18, 58)

    def configure(self, state: BuildState):
        opts = state.options
        opts['CMAKE_OSX_ARCHITECTURES'] = 'x86_64;arm64'
        # Workaround for removed PythonInterp CMake module
        opts['PYTHON_EXECUTABLE'] = '/usr/bin/python3'

        super().configure(state)
