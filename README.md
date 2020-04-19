# walrus

[![PyPI - Downloads](https://pepy.tech/badge/python-walrus)](https://pepy.tech/count/python-walrus)
[![PyPI - Version](https://img.shields.io/pypi/v/python-walrus.svg)](https://pypi.org/project/python-walrus)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/python-walrus.svg)](https://pypi.org/project/python-walrus)

[![Travis CI - Status](https://img.shields.io/travis/pybpc/walrus.svg)](https://travis-ci.org/pybpc/walrus)
[![Codecov - Coverage](https://codecov.io/gh/pybpc/walrus/branch/master/graph/badge.svg)](https://codecov.io/gh/pybpc/walrus)
[![Documentation Status](https://readthedocs.org/projects/bpc-walrus/badge/?version=latest)](https://bpc-walrus.readthedocs.io/en/latest/)
<!-- [![LICENSE](https://img.shields.io/badge/license-Anti%20996-blue.svg)](https://github.com/996icu/996.ICU/blob/master/LICENSE) -->

> Write *assignment expressions* in Python 3.8 flavour, and let `walrus` worry about back-port issues :beer:

&emsp; Since [PEP 572](https://www.python.org/dev/peps/pep-0572/), Python introduced *assignment expressions*
syntax in version __3.8__. For those who wish to use *assignment expressions* in their code, `walrus` provides an
intelligent, yet imperfect, solution of a **backport compiler** by replacing *assignment expressions* syntax with
old-fashioned assignment-then-conditional syntax, which guarantees you to always write *assignment expressions* in
Python 3.8 flavour then compile for compatibility later.

## Installation

> Note that `walrus` only supports Python versions __since 3.4__ 🐍

&emsp; For macOS users, `walrus` is now available through [Homebrew](https://brew.sh):

```sh
brew tap jarryshaw/tap
brew install walrus
# or simply, a one-liner
brew install jarryshaw/tap/walrus
```

&emsp; Simply run the following to install the current version from PyPI:

```sh
pip install python-walrus
```

&emsp; Or install the latest version from the git repository:

```sh
git clone https://github.com/pybpc/walrus.git
cd walrus
pip install -e .
# and to update at any time
git pull
```

## Basic Usage

### CLI

&emsp; It is fairly straightforward to use `walrus`:

> context in `${...}` changes dynamically according to runtime environment

```text
usage: walrus [options] <Python source files and directories...>

Back-port compiler for Python 3.8 assignment expressions.

positional arguments:
  <Python source files and directories...>
                        Python source files and directories to be converted

optional arguments:
  -h, --help            show this help message and exit
  -V, --version         show program's version number and exit
  -q, --quiet           run in quiet mode
  -C N, --concurrency N
                        the number of concurrent processes for conversion
  --dry-run             list the files to be converted without actually performing conversion and archiving

archive options:
  backup original files in case there're any issues

  -na, --no-archive     do not archive original files
  -k PATH, --archive-path PATH
                        path to archive original files
  -r ARCHIVE_FILE, --recover ARCHIVE_FILE
                        recover files from a given archive file
  -r2                   remove the archive file after recovery
  -r3                   remove the archive file after recovery, and remove the archive directory if it becomes empty

convert options:
  conversion configuration

  -vs VERSION, -vf VERSION, --source-version VERSION, --from-version VERSION
                        parse source code as this Python version
  -l LINESEP, --linesep LINESEP
                        line separator (LF, CRLF, CR) to read source files
  -t INDENT, --indentation INDENT
                        code indentation style, specify an integer for the number of spaces, or 't'/'tab' for tabs
  -n8, --no-pep8        do not make code insertion PEP 8 compliant
```

&emsp; Normally you will just call `walrus .`, then `walrus` will read and convert all *assignment expressions* syntax in every Python
file under the current working directory. In case there might be some problems with the conversion, `walrus` will
backup all original files it is to modify into the `archive` directory ahead of the process,
if the `-na` option is not set.

### Configuration

`walrus` currently supports following environment variables:

- `WALRUS_QUIET` -- same as the `quiet` option in CLI
- `WALRUS_DO_ARCHIVE` -- same as the `do-archive` option in CLI (logical negation)
- `WALRUS_ARCHIVE_PATH` -- same as the `archive-path` option in CLI
- `WALRUS_SOURCE_VERSION` -- same as the `source-version` option in CLI
- `WALRUS_LINESEP` -- same as the `linesep` option in CLI
- `WALRUS_INDENTATION` -- same as the `indentation` option in CLI
- `WALRUS_PEP8` -- same as the `no-pep8` option in CLI (logical negation)

## Test

&emsp; See [`tests`](https://github.com/pybpc/walrus/blob/master/tests) directory.

## Known issues

&emsp; Since `walrus` is currently based on [`parso`](https://github.com/davidhalter/parso) project,
it had encountered several compatibility and parsing issues.

* ~~Parsing f-strings with format spec beginning with `=` produces incorrect SyntaxError ([#89](https://github.com/davidhalter/parso/issues/89))~~
  This issue has been resolved since `parso` version __0.5.2__.

* ~~Parsing invalid use cases of assignment expressions do not raise SyntaxError ([#89](https://github.com/davidhalter/parso/issues/89))~~
  This issue has been resolved since `parso` version __0.5.2__.

## Contribution

&emsp; Contributions are very welcome, especially fixing bugs and providing test cases.
Note that code must remain valid and reasonable.

## See Also

- [`pybpc`](https://github.com/pybpc/bpc) (formerly known as `python-babel`)
- [`f2format`](https://github.com/pybpc/f2format)
- [`poseur`](https://github.com/pybpc/poseur)
- [`vermin`](https://github.com/netromdk/vermin)
