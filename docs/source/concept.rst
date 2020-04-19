Algorithms
==========

As discussed in :pep:`572`, *assignment expression* is a way to assign to variables within
an expression using the notation ``NAME := expr``. It is roughly equivalent to first assign
``expr`` to the variable ``NAME``, then reference such variable ``NAME`` at the current
code context.

Basic Concepts
--------------

To convert, :mod:`walrus` will need to evaluate the expression then assign to the variable,
make sure such variable is available from the current namespace and replace the original
*assignment expressions* with the assigned variable.

For example, with the samples from :pep:`572`:

.. code:: python

   # Handle a matched regex
   if (match := pattern.search(data)) is not None:
       # Do something with match

it should be converted to

.. code:: python

   # Handle a matched regex
   match = pattern.search(data)
   if (match) is not None:
       # Do something with match

However, such implementation is **NOT** generic for *assignment expressions* in more
complex grammars and contexts, such as comprehensions per
:pep:`Appendix B <572#appendix-b-rough-code-translations-for-comprehensions>`:

.. code:: python

   a = [TARGET := EXPR for VAR in ITERABLE]

For a more *generic* implementation, :mod:`walrus` wraps the assignment operation as a
function, and utilises :token:`global <global_stmt>` and :token:`nonlocal <nonlocal_stmt>`
keywords to inject such assigned variable back into the original context namespace.

For instance, it should convert the first example to

.. code:: python

   # in case ``match`` is not defined
   if False:
       match = NotImplemented

   def wraps(expr):
       """Wrapper function."""
       global match  # assume we're at module level
       match = expr
       return match

   # Handle a matched regex
   if (wraps(pattern.search(data))) is not None:
       # Do something with match

The original *assignment expression* is replaced with a wrapper function call, which
takes the original expression part as parameter. And in the wrapper function, it
assign the value of the expression to the original variable, then inject such variable
into outer scope (:term:`namespace`) with :token:`global <global_stmt>` and/or
:token:`nonlocal <nonlocal_stmt>` keyword depending on current context, and finally
returns the assigned variable so that the wrapper function call works exactly as before.

.. seealso::

   * variable declration -- :data:`walrus.NAME_TEMPLATE`
   * wrapper function call -- :data:`walrus.CALL_TEMPLATE`
   * wrapper function definition -- :data:`walrus.FUNC_TEMPLATE`

Keyword Selection
~~~~~~~~~~~~~~~~~

Python provides :token:`global <global_stmt>` and :token:`nonlocal <nonlocal_stmt>`
keywords for interacting with variables not in current namespace. Following the Python
grammar definitions, :mod:`walrus` selects the keyword in the mechanism described below:

0. If current context is at module level, i.e. neither inside a :term:`function` nor a
   :term:`class` definition, then :token:`global <global_stmt>` should be used.
1. If current context is at :term:`function` level and the variable is not declared in
   any :token:`global <global_stmt>` statements, then :token:`nonlocal <nonlocal_stmt>`
   should be used; otherwise :token:`global <global_stmt>` should be used.
2. If current context is at :term:`class` level and not in its :term:`method` definition,
   i.e. in the :term:`class` body, it shall be treated as a special case.

Nevertheless, for assignment expression in :term:`lambda` statements, it shall be treated
as another special case.

Lambda Statements
-----------------

Class Definitions
-----------------
