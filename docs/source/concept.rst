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

0. If current context is at :term:`module` level, i.e. neither inside a :term:`function`
   nor a :term:`class` definition, then :token:`global <global_stmt>` should be used.
1. If current context is at :term:`function` level and the variable is not declared in
   any :token:`global <global_stmt>` statements, then :token:`nonlocal <nonlocal_stmt>`
   should be used; otherwise :token:`global <global_stmt>` should be used.
2. If current context is at :term:`class` level and not in its :term:`method` definition,
   i.e. in the :term:`class` body, it shall be treated as a special case.

Nevertheless, for assignment expression in :term:`lambda` statements, it shall be treated
as another special case.

Lambda Statements
-----------------

The :term:`lambda` statements can always be transformed as a regular :term:`function`.
This is the foundation of converting *assignment expressions* in a :term:`lambda` statement.

For a sample :term:`lambda` statement as following:

.. code:: python

   >>> foo = lambda: [x := i ** 2 for i in range(10)]
   >>> foo()
   [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]

:mod:`walrus` will transform the original :term:`lambda` statement into a function first:

.. code:: python

   def foo():
       return [x := i ** 2 for i in range(10)]

And now, :mod:`walrus` can simply apply the generic conversion templates to replace the
*assignment expressions* with a wrapper function:

.. code:: python

   def foo():
       if False:
           x = NotImplemented

       def wraps(expr):
           """Wrapper function."""
           nonlocal x  # assume that ``x`` never declared by ``global``
           x = expr
           return x

       return [wraps(i ** 2) for i in range(10)]

.. seealso::

   * :data:`walrus.LAMBDA_CALL_TEMPLATE`
   * :data:`walrus.LAMBDA_FUNC_TEMPLATE`

Class Definitions
-----------------

As the :term:`class` context is slightly different from regular :term:`module`
and/or :term:`function` context, the generic conversion templates are **NOT**
applicable to such scenarios.

.. note::

   For :term:`method` context in the :term:`class` body, it is will applicable
   with the generic conversion templates. In this section, we are generally
   discussing conversion related to *class variables*.

Given a :term:`class` definition as following:

.. code:: python

   class A:

       bar = (foo := x ** 2)

:mod:`walrus` will rewrite all *class variables* in the current context:

.. code:: python

   # temporary namespace for class context
   namespace = dict()

   class A:

       def wraps(expr):
           """Wrapper function."""
           namespace['foo'] = expr
           return namespace['foo']

       # assign to temporary namespace
       namespace['bar'] = wraps(x ** 2)

   # set attributes from temporary namespace
   [setattr(A, k, v) for k, v in namespace.items()]
   del namespace

The major reason of doing so is that the :term:`class` name is not available
in its context, i.e. we cannot directly assign :attr:`A.foo` in the :meth:`A.wraps`
method. Rewriting all assignment and reference to *class variables* as operations
to the ``namespace`` dictionary grants :mod:`walrus` an efficiently to synchronise
all changes to such variables.

However, if a variable is declared in :token:`global <global_stmt>` and/or
:token:`nonlocal <nonlocal_stmt>` statements, it is **NOT** supposed to be assigned
to the :term:`class` context, rather the outer scope (:term:`namespace`).

.. seealso::

   * :data:`walrus.LCL_DICT_TEMPLATE`
   * :data:`walrus.LCL_NAME_TEMPLATE`
   * :data:`walrus.LCL_CALL_TEMPLATE`
   * :data:`walrus.LCL_VARS_TEMPLATE`
   * :data:`walrus.CLS_CALL_TEMPLATE`
   * :data:`walrus.CLS_NAME_TEMPLATE`
   * :data:`walrus.CLS_SET_FUNC_TEMPLATE`
   * :data:`walrus.CLS_GET_FUNC_TEMPLATE`
   * :data:`walrus.CLS_EXT_CALL_TEMPLATE`
   * :data:`walrus.CLS_EXT_FUNC_TEMPLATE`
   * :data:`walrus.CLS_EXT_VARS_GLOBAL_TEMPLATE`
   * :data:`walrus.CLS_EXT_VARS_NONLOCAL_TEMPLATE`
