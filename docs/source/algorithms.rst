Algorithms
==========

As discussed in :pep:`572`, *assignment expression* is a way to assign to variables within
an expression using the notation ``NAME := expr``. It is roughly equivalent to first assigning
``expr`` to the variable ``NAME``, then referencing such variable ``NAME`` at the current scope.

Basic Concepts
--------------

To convert, ``walrus`` will need to evaluate the expression, assign to the variable,
make sure such variable is available from the current scope and replace the original
*assignment expression* with code using pre-3.8 syntax.

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

For a more *generic* implementation, ``walrus`` wraps the assignment operation as a
function, and utilises :token:`global <global_stmt>` and :token:`nonlocal <nonlocal_stmt>`
keywords to inject such assigned variable back into the original scope.

For instance, it should convert the first example to

.. code:: python

   # make sure to define ``match`` in this scope
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
takes the original expression part as a parameter. And in the wrapper function, it
assigns the value of the expression to the original variable, and then injects such variable
into outer scope (:term:`namespace`) with :token:`global <global_stmt>` and/or
:token:`nonlocal <nonlocal_stmt>` keyword depending on current context, and finally
returns the assigned variable so that the wrapper function call works exactly as if
we were using an *assignment expression*.

.. seealso::

   * variable declaration -- :data:`walrus.NAME_TEMPLATE`
   * wrapper function call -- :data:`walrus.CALL_TEMPLATE`
   * wrapper function definition -- :data:`walrus.FUNC_TEMPLATE`

Keyword Selection
~~~~~~~~~~~~~~~~~

Python provides :token:`global <global_stmt>` and :token:`nonlocal <nonlocal_stmt>`
keywords for interacting with variables not in the current namespace. Following the Python
grammar definitions, ``walrus`` selects the keyword in the mechanism described below:

1. If current context is at :term:`module` level, i.e. neither inside a :term:`function`
   nor a :term:`class` definition, then :token:`global <global_stmt>` should be used.
2. If current context is at :term:`function` level and the variable is not declared in
   any :token:`global <global_stmt>` statements, then :token:`nonlocal <nonlocal_stmt>`
   should be used; otherwise :token:`global <global_stmt>` should be used.
3. If current context is at :term:`class` level and not in its :term:`method` definition,
   i.e. in the :term:`class` body, it shall be treated as a special case.

For assignment expression in :term:`lambda` functions, it shall be treated as another
special case.

Lambda Functions
----------------

:term:`lambda` functions can always be transformed into a regular :term:`function`.
This is the foundation of converting *assignment expressions* in :term:`lambda` functions.

For a sample :term:`lambda` function as follows:

.. code:: python

   >>> foo = lambda: [x := i ** 2 for i in range(10)]
   >>> foo()
   [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]

``walrus`` will transform the original :term:`lambda` function into a regular function first:

.. code:: python

   def foo():
       return [x := i ** 2 for i in range(10)]

And now, ``walrus`` can simply apply the generic conversion strategies to replace the
*assignment expression* with a wrapper function:

.. code:: python

   def foo():
       if False:
           x = NotImplemented

       def wraps(expr):
           """Wrapper function."""
           nonlocal x  # assume that ``x`` was not declared as ``global``
           x = expr
           return x

       return [wraps(i ** 2) for i in range(10)]

.. seealso::

   * :data:`walrus.LAMBDA_CALL_TEMPLATE`
   * :data:`walrus.LAMBDA_FUNC_TEMPLATE`

Class Definitions
-----------------

As the :term:`class` context is slightly different from regular :term:`module`
and/or :term:`function` contexts, the generic conversion strategies are **NOT**
applicable to such scenarios.

.. note::

   For :term:`method` context in the :term:`class` body, the generic conversion
   strategies are still applicable. In this section, we are generally
   discussing conversion related to *class variables*.

Given a :term:`class` definition as following:

.. code:: python

   class A:
       bar = (foo := x ** 2)

``walrus`` will rewrite all *class variables* in the current context:

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

The major reason of doing so is that the :term:`class` is not available
in its context, i.e. we cannot directly assign :attr:`A.foo` in the :meth:`A.wraps`
method. Rewriting all assignments and references to *class variables* as operations
to the ``namespace`` dictionary grants ``walrus`` an efficiently to synchronise
all changes to such variables.

However, if a variable is declared in :token:`global <global_stmt>` and/or
:token:`nonlocal <nonlocal_stmt>` statements, it is **NOT** supposed to be assigned
to the :term:`class` context, rather it should go to the outer scope (:term:`namespace`).

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
