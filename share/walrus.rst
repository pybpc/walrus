======
walrus
======

-------------------------------------------------------
back-port compiler for Python 3.8 assignment expression
-------------------------------------------------------

:Version: v0.1.5rc1
:Date: April 02, 2021
:Manual section: 1
:Author:
    Contributors of the Python Backport Compiler project.
    See https://github.com/pybpc
:Copyright:
    *walrus* is licensed under the **MIT License**.

SYNOPSIS
========

walrus [*options*] <*Python source files and directories...*>

DESCRIPTION
===========

Since PEP 572, Python introduced *assignment expressions* syntax in
version __3.8__. For those who wish to use *assignment expressions*
in their code, ``walrus`` provides an intelligent, yet imperfect,
solution of a **backport compiler** by replacing *assignment expressions*
syntax with old-fashioned syntax, which guarantees you to always write
*assignment expressions* in Python 3.8 flavour then compile for
compatibility later.

This man page mainly introduces the CLI options of the ``walrus`` program.
You can also checkout the online documentation at
https://bpc-walrus.readthedocs.io/ for more details.

OPTIONS
=======

positional arguments
--------------------

:SOURCE:                Python source files and directories to be converted

optional arguments
------------------

-h, --help              show this help message and exit
-V, --version           show program's version number and exit
-q, --quiet             run in quiet mode

-C *N*, --concurrency *N*
                        the number of concurrent processes for conversion

--dry-run               list the files to be converted without actually performing conversion and archiving

-s *[FILE]*, --simple *[FILE]*
                        this option tells the program to operate in "simple mode"; if a file name is provided, the program will convert
                        the file but print conversion result to standard output instead of overwriting the file; if no file names are
                        provided, read code for conversion from standard input and print conversion result to standard output; in
                        "simple mode", no file names shall be provided via positional arguments

archive options
---------------

backup original files in case there're any issues

-na, --no-archive       do not archive original files

-k *PATH*, --archive-path *PATH*
                        path to archive original files

-r *ARCHIVE_FILE*, --recover *ARCHIVE_FILE*
                        recover files from a given archive file

-r2                     remove the archive file after recovery
-r3                     remove the archive file after recovery, and remove the archive directory if it becomes empty

convert options
---------------

conversion configuration

-vs *VERSION*, --vf *VERSION*, --source-version *VERSION*, --from-version *VERSION*
                        parse source code as this Python version

-l *LINESEP*, --linesep *LINESEP*
                        line separator (**LF**, **CRLF**, **CR**) to read source files

-t *INDENT*, --indentation *INDENT*
                        code indentation style, specify an integer for the number of spaces, or ``'t'``/``'tab'`` for tabs

-n8, --no-pep8          do not make code insertion **PEP 8** compliant

ENVIRONMENT
===========

``walrus`` currently supports these environment variables:

:WALRUS_QUIET:           run in quiet mode
:WALRUS_CONCURRENCY:     the number of concurrent processes for conversion
:WALRUS_DO_ARCHIVE:      whether to perform archiving
:WALRUS_ARCHIVE_PATH:    path to archive original files
:WALRUS_SOURCE_VERSION:  parse source code as this Python version
:WALRUS_LINESEP:         line separator to read source files
:WALRUS_INDENTATION:     code indentation style
:WALRUS_PEP8:            whether to make code insertion **PEP 8** compliant

SEE ALSO
========

pybpc(1), f2format(1), poseur(1), vermin(1)
