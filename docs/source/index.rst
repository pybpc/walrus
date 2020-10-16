.. walrus documentation master file, created by
   sphinx-quickstart on Sat Apr 11 11:06:46 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

``walrus`` - Backport Compiler for Assignment Expressions
=========================================================

   Write *assignment expressions* in Python 3.8 flavour, and let ``walrus`` worry about back-port issues |:beer:|

Since :pep:`572`, Python introduced *assignment expressions* syntax in version **3.8**. For those who wish to use
*assignment expressions* in their code, ``walrus`` provides an intelligent, yet imperfect, solution of a
**backport compiler** by replacing *assignment expressions* syntax with old-fashioned syntax, which guarantees
you to always write *assignment expressions* in Python 3.8 flavour then compile for compatibility later.

.. toctree::
   :maxdepth: 3

   usage
   algorithms
   api

------------
Installation
------------

.. note::

   ``walrus`` only supports Python versions **since 3.4** |:snake:|

For macOS users, ``walrus`` is available through `Homebrew`_:

.. code-block:: shell

   brew tap jarryshaw/tap
   brew install walrus
   # or simply, a one-liner
   brew install jarryshaw/tap/walrus

You can also install from `PyPI`_ for any OS:

.. code-block:: shell

   pip install bpc-walrus

Or install the latest version from the `Git repository`_:

.. code-block:: shell

   git clone https://github.com/pybpc/walrus.git
   cd walrus
   pip install -e .
   # and to update at any time
   git pull

.. note::
   Installation from `Homebrew`_ will also automatically install the man page and
   `Bash Completion`_ script for you. If you are installing from `PyPI`_ or
   the `Git repository`_, you can install the completion script manually.

.. _Homebrew: https://brew.sh
.. _PyPI: https://pypi.org/project/python-walrus
.. _Git repository: https://github.com/pybpc/walrus
.. _Bash Completion: https://github.com/pybpc/walrus/blob/master/share/walrus.bash-completion

-----
Usage
-----

See :doc:`usage`.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
