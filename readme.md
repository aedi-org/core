# Core module to build various libraries and tools for macOS

## Usage

Download source code, and build a target

```sh
build.py --target=<target-name>
```

Build target from existing source code

```sh
build.py --source=<path-to-source-code>
```

Generate Xcode project instead of building target, and open it

```sh
build.py --source=...|--target=... --xcode
```

Run `build.py` without arguments for complete list of options.

## Prerequisites

Xcode 12.2 or newer is required in order to build universal binaries. Launch Xcode once to finish its installation. In theory, it is possible to use older versions of Xcode to build Intel target only by adding `--disable-arm` command line option.

## Directories

* `build` directory stores all intermediary files created during targets compilation, customizable with `--build-path` command line option
* `deps` directory stores all dependencies (headers, libraries, executable and additional files) in the corresponding subdirectories
* `output` directory stores built main targets, customizable with `--output-path` command line option
* `prefix` directory stores symbolic links to all dependencies combined as one build root
* `sdk` directory can contain macOS SDKs that will be picked if match with macOS deployment versions
* `source` directory stores targets source code, customizable with `--source-path` command line option
* `temp` directory stores temporary files, customizable with `--temp-path` command line option

## Projects

* [games-macos-deps](https://github.com/aedi-org/games-macos-deps), games libraries and tools
* [misc-macos-deps](https://github.com/aedi-org/misc-macos-deps), miscellaneous libraries and tools
* [rfreq-macos-deps](https://github.com/aedi-org/rfreq-macos-deps), radio frequency libraries and tools
* [zdoom-macos-deps](https://github.com/ZDoom/zdoom-macos-deps), *ZDoom binary dependencies

## Previous development

The initial development of `aedi` Python module was performed in [zdoom-macos-deps](https://github.com/ZDoom/zdoom-macos-deps) repository. The last commit before migration to Git submodule usage was [9af10bc](https://github.com/ZDoom/zdoom-macos-deps/commit/9af10bcbcd2a3e734866714803eb098033cc1217).

## Attributions

Organization icon is one of [Build icons](https://www.flaticon.com/free-icons/build) created by [Smashicons](https://www.flaticon.com/authors/smashicons) and hosted by [Flaticon](https://www.flaticon.com).
