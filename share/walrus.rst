======
walrus
======

-------------------------------------------------------
back-port compiler for Python 3.8 assignment expression
-------------------------------------------------------

:Version: v0.3.1
:Date: October 24, 2019
:Manual section: 1
:Author:
    Jarry Shaw, a newbie programmer, is the author, owner and maintainer
    of *walrus*. Please contact me at *jarryshaw@icloud.com*.
:Copyright:
    *walrus* is licensed under the **MIT License**.

SYNOPSIS
========

walrus [*options*] <*python source files and folders*> ...

DESCRIPTION
===========



OPTIONS
=======

positional arguments
--------------------

:SOURCE:              python source files and folders to be converted

optional arguments
------------------

-h, --help            show this help message and exit
-V, --version         show program's version number and exit
-q, --quiet           run in quiet mode

archive options
---------------

duplicate original files in case there's any issue

-na, --no-archive     do not archive original files

-p *PATH*, --archive-path *PATH*
                      path to archive original files

convert options
---------------

compatibility configuration for none-unicode files

-c *CODING*, --encoding *CODING*
                      encoding to open source files

-v *VERSION*, --python *VERSION*
                      convert against Python version

-s *SEP*, --linesep *SEP*
                      line separator to process source files

-nl, --no-linting     do not lint converted codes

ENVIRONMENT
===========

``walrus`` currently supports two environment variables.

:WALRUS_QUIET:        run in quiet mode
:WALRUS_ENCODING:     encoding to open source files
:WALRUS_VERSION:      convert against Python version
:WALRUS_LINESEP:      line separator to process source files
:WALRUS_LINTING:      lint converted codes

SEE ALSO
========

babel(1), f2format(1), poseur(1), vermin(1)
