.. walrus documentation master file, created by
   sphinx-quickstart on Sat Apr 11 11:06:46 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to walrus's documentation!
==================================

Write *assignment expressions* in Python 3.8 flavour, and let :mod:`walrus` worry about back-port issues |:beer:|

.. toctree::
   :maxdepth: 3

   api

Since :pep:`572`, Python introduced *assignment expressions* syntax in version **3.8**. For those who wish to use
*assignment expressions* in their code, :mod:`walrus` provides an intelligent, yet imperfect, solution of a
**backport compiler** by replacing *assignment expressions* syntax with old-fashioned assignment-then-conditional
syntax, which guarantees you to always write *assignment expressions* in Python 3.8 flavour then compile for
compatibility later.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
