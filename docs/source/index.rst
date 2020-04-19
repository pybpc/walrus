.. walrus documentation master file, created by
   sphinx-quickstart on Sat Apr 11 11:06:46 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

:mod:`walrus` - Backport Compiler for Assignment Expressions
============================================================

   Write *assignment expressions* in Python 3.8 flavour, and let :mod:`walrus` worry about back-port issues |:beer:|

Since :pep:`572`, Python introduced *assignment expressions* syntax in version **3.8**. For those who wish to use
*assignment expressions* in their code, :mod:`walrus` provides an intelligent, yet imperfect, solution of a
**backport compiler** by replacing *assignment expressions* syntax with old-fashioned assignment-then-conditional
syntax, which guarantees you to always write *assignment expressions* in Python 3.8 flavour then compile for
compatibility later.

.. toctree::
   :maxdepth: 3

   api
   example

------------
Installation
------------

.. note::

   :mod:`walrus` only supports Python versions **since 3.4** |:snake:|

For macOS users, :mod:`walrus` is now available through `Homebrew`_:

.. code:: shell

   brew tap jarryshaw/tap
   brew install walrus
   # or simply, a one-liner
   brew install jarryshaw/tap/walrus

Simple run the following to install the current version from `PyPI`_:

.. code:: shell

   pip install python-walrus

Or install the latest version from the `Git repository`_:

.. code:: shell

   git clone https://github.com/pybpc/walrus.git
   cd walrus
   pip install -e .
   # and to update at any time
   git pull

.. _Homebrew: https://brew.sh
.. _PyPI: https://pypi.org/project/python-walrus
.. _Git repository: https://github.com/pybpc/walrus

-----------
Basic Usage
-----------

CLI
---

It is fairly straightforward to use :mod:`walrus`:

.. note:: context in ``${...}`` changes dynamically according to runtime environment

.. code:: text

   usage: walrus [options] <Python source files and directories...>

   Back-port compiler for Python 3.8 assignment expressions.

   positional arguments:
     SOURCE                Python source files and directories to be converted

   optional arguments:
     -h, --help            show this help message and exit
     -V, --version         show program's version number and exit
     -q, --quiet           run in quiet mode

   archive options:
     backup original files in case there're any issues

     -na, --no-archive     do not archive original files
     -p PATH, --archive-path PATH
                           path to archive original files (${PWD}/archive)

   convert options:
     conversion configuration

     -sv VERSION, -fv VERSION, --source-version VERSION, --from-version VERSION
                           parse source code as Python version (${LATEST_VERSION})
     -s SEP, --linesep SEP
                           line separator (LF, CRLF, CR) to read source files (auto detect)
     -t INDENT, --indentation INDENT
                           code indentation style, specify an integer for the number of spaces, or 't'/'tab' for tabs (auto detect)
     -n8, --no-pep8        do not make code insertion PEP 8 compliant

Normally you will just call ``walrus .``, then mod:`walrus` will read and convert all *assignment expressions* syntax in every
Python file under the current working directory. In case there might be some problems with the
conversion, :mod:`walrus` will backup all original files it is to modify into
the ``archive`` directory ahead of the process, if the ``-na`` option is not set.

Configuration
-------------

:mod:`walrus` currently supports following environment variables:

.. envvar:: WALRUS_QUIET

   Same as the ``quiet`` option in CLI.

.. envvar:: WALRUS_DO_ARCHIVE

   Same as the ``do-archive`` option in CLI (logical negation).

.. envvar:: WALRUS_ARCHIVE_PATH

   Same as the ``archive-path`` option in CLI.

.. envvar:: WALRUS_SOURCE_VERSION

   Same as the ``source-version`` option in CLI.

.. envvar:: WALRUS_LINESEP

   Same as the ``linesep`` option in CLI.

.. envvar:: WALRUS_INDENTATION

   Same as the ``indentation`` option in CLI.

.. envvar:: WALRUS_PEP8

   Same as the ``no-pep8`` option in CLI (logical negation).

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
