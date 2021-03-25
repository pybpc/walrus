API Reference
=============

.. module:: walrus

.. .. automodule:: walrus
..    :members:
..    :undoc-members:
..    :show-inheritance:

Public Interface
----------------

.. autofunction:: walrus.convert

.. autofunction:: walrus.walrus

.. autofunction:: walrus.main

Conversion Implementation
-------------------------

The main logic of the ``walrus`` conversion is to wrap *assignment expressions*
as functions which manipulates variable namespaces to implement the **assignment**
part and evaluates original code blocks to archive the **expression** part.

For conversion algorithms and details, please refer to :doc:`algorithms`.

Data Structures
~~~~~~~~~~~~~~~

During conversion, we utilised :class:`bpc_utils.Config` to store and deliver the
configurations over the conversion :class:`~walrus.Context` instances, which should
be as following:

.. class:: Config

   Configuration object shared over the conversion process of a single source file.

   .. attribute:: indentation
      :type: str

      Indentation sequence.

   .. attribute:: linesep
      :type: Literal[\'\\n\', \'\\r\\n\', \'\\r\']

      Line separator.

   .. attribute:: pep8
      :type: bool

      :pep:`8` compliant conversion flag.

   .. attribute:: filename
      :type: Optional[str]

      An optional source file name to provide a context in case of error.

   .. attribute:: source_version
      :type: Optional[str]

      Parse the code as this Python version (uses the latest version by default).

Since conversion of assignment expressions in different statements has different
processing logics and templates, we hereby describe two data structures representing
such information.

The :class:`FunctionEntry` represents an assignment expression at most circumstances. It
will be provided to :data:`~walrus.FUNC_TEMPLATE` to render the wrapper function for
the conversion.

.. class:: FunctionEntry

   :bases: :class:`typing.TypedDict`

   .. attribute:: name
      :type: str

      Function name, as the original *left-hand-side* variable name
      from the assignment expression.

   .. attribute:: uuid
      :type: str

      UUID text in the function name to avoid name collision with existing functions.

   .. attribute:: scope_keyword
      :type: Literal[\'global\', \'nonlocal\']

      Scope manipulation keyword. If :attr:`name` is declared in *global*
      namespace, then it will be ``'global'``, else ``'nonlocal'``.

      .. note::
         If the *left-hand-side* variable name is recorded in the global context
         (:attr:`Context.global_stmt`), then the converted function should use
         ``'global'`` as its scope keyword.

The :class:`LambdaEntry` represents an assignment expression declared in *lambda*
statements. It will be provided to :data:`~walrus.LAMBDA_FUNC_TEMPLATE` to render
the wrapper function for the conversion.

.. class:: LambdaEntry

   :bases: :class:`typing.TypedDict`

   .. attribute:: param
      :type: str

      Concatenated parameter string for the wrapper function.

   .. attribute:: suite
      :type: str

      Original *lambda* suite with assignment expressions converted.

   .. attribute:: uuid
      :type: str

      UUID text in the function name to avoid name collision with existing functions.

Conversion Templates
~~~~~~~~~~~~~~~~~~~~

For general conversion scenarios, the converted wrapper functions will be
rendered based on the following templates.

.. data:: NAME_TEMPLATE
   :type: List[str]

   .. code-block:: python

      ['if False:',
       '%(indentation)s%(name_list)s = NotImplemented']

   Declares variables in the current scope for using ``global`` and/or
   ``nonlocal`` statements.

   :Variables:
      * **indentation** -- indentation sequence as defined in
        :attr:`Config.indentation <walrus.Config.indentation>`
      * **name_list** -- equal (``=``) separated list of variable names

   .. important::

      This is a rather hack way to fool the Python interpreter that such
      variables had been declared in the current scope, whilst not actually
      declaring such variables at runtime.

.. data:: CALL_TEMPLATE
   :type: str

   .. code-block:: python

      '_walrus_wrapper_%(name)s_%(uuid)s(%(expr)s)'

   Wrapper function call to replace the original assignment expression.

   :Variables:
      * **name** -- *left-hand-side* variable name
      * **uuid** -- UUID text
      * **expr** -- *right-hand-side* expression

.. data:: FUNC_TEMPLATE
   :type: List[str]

   .. code-block:: python

      ['def _walrus_wrapper_%(name)s_%(uuid)s(expr):',
       '%(indentation)s"""Wrapper function for assignment expression."""',
       '%(indentation)s%(scope_keyword)s %(name)s',
       '%(indentation)s%(name)s = expr',
       '%(indentation)sreturn %(name)s']

   Wrapper function call to replace the original assignment expression.

   :Variables:
      * **indentation** -- indentation sequence as defined in
        :attr:`Config.indentation <walrus.Config.indentation>`
      * \*\*\ **kwargs** -- function record as described in :class:`Function`

For assignment expression in *lambda* expressions, the converted wrapper
function will be rendered based on the following templates.

.. data:: LAMBDA_CALL_TEMPLATE
   :type: str

   .. code-block:: python

      '_walrus_wrapper_lambda_%(uuid)s'

   Wrapper function call to replace the original assignment expression.

   :Variables:
      * **uuid** -- UUID text

.. data:: LAMBDA_FUNC_TEMPLATE
   :type: List[str]

   .. code-block:: python

      ['def _walrus_wrapper_lambda_%(uuid)s(%(param)s):',
       '%(indentation)s"""Wrapper function for lambda definitions."""',
       '%(indentation)s%(suite)s']

   Wrapper function call to replace the original assignment expression.

   :Variables:
      * **indentation** -- indentation sequence as defined in
        :attr:`Config.indentation <walrus.Config.indentation>`
      * \*\*\ **kwargs** -- function record as described in :class:`LambdaEntry`

For assignment expression in :term:`class variables <class-variable>`
(``ClassVar``), the converted wrapper function will be rendered based on
the following templates.

.. data:: CLS_TEMPLATE
   :type: str

   .. code-block:: python

      "(__import__('builtins').locals().__setitem__(%(name)r, %(expr)s), %(name)s)[1]"

   *One-liner* to rewrite the original assignment expression for
   a *regular* :term:`class variable <class-variable>` definition.

   :Variables:
      * **name** -- variable name
      * **expr** -- original *right-hand-side* expression

.. note::

   If a wrapper function and/or class involves manipulation over the
   :token:`global <global_stmt>` and :token:`nonlocal <nonlocal_stmt>`
   statements, then ``walrus`` will append a UUID exclusively.

Conversion Contexts
~~~~~~~~~~~~~~~~~~~

.. autoclass:: walrus.Context
   :members:
   :undoc-members:
   :private-members:
   :show-inheritance:

.. autoclass:: walrus.StringContext
   :members:
   :undoc-members:
   :private-members:
   :show-inheritance:

.. autoclass:: walrus.LambdaContext
   :members:
   :undoc-members:
   :private-members:
   :show-inheritance:

.. autoclass:: walrus.ClassContext
   :members:
   :undoc-members:
   :private-members:
   :show-inheritance:

.. autoclass:: walrus.ClassStringContext
   :members:
   :undoc-members:
   :private-members:
   :show-inheritance:

Internal Auxiliaries
--------------------

Options & Defaults
~~~~~~~~~~~~~~~~~~

.. autodata:: walrus.WALRUS_SOURCE_VERSIONS

Below are option getter utility functions. Option value precedence is::

   explicit value (CLI/API arguments) > environment variable > default value

.. autofunction:: walrus._get_quiet_option
.. autofunction:: walrus._get_concurrency_option
.. autofunction:: walrus._get_do_archive_option
.. autofunction:: walrus._get_archive_path_option
.. autofunction:: walrus._get_source_version_option
.. autofunction:: walrus._get_linesep_option
.. autofunction:: walrus._get_indentation_option
.. autofunction:: walrus._get_pep8_option

The following variables are used for fallback default values of options.

.. autodata:: walrus._default_quiet
.. autodata:: walrus._default_concurrency
.. autodata:: walrus._default_do_archive
.. autodata:: walrus._default_archive_path
.. autodata:: walrus._default_source_version
.. autodata:: walrus._default_linesep
.. autodata:: walrus._default_indentation
.. autodata:: walrus._default_pep8

.. important::

   For :data:`_default_concurrency`, :data:`_default_linesep` and :data:`_default_indentation`,
   :data:`None` means *auto detection* during runtime.

CLI Utilities
~~~~~~~~~~~~~

.. autofunction:: walrus.get_parser

The following variables are used for help messages in the argument parser.

.. data:: walrus.__cwd__
   :type: str

   Current working directory returned by :func:`os.getcwd`.

.. data:: walrus.__walrus_quiet__
   :type: Literal[\'quiet mode\', \'non-quiet mode\']

   Default value for the ``--quiet`` option.

   .. seealso:: :func:`walrus._get_quiet_option`

.. data:: walrus.__walrus_concurrency__
   :type: Union[int, Literal[\'auto detect\']]

   Default value for the ``--concurrency`` option.

   .. seealso:: :func:`walrus._get_concurrency_option`

.. data:: walrus.__walrus_do_archive__
   :type: Literal[\'will do archive\', \'will not do archive\']

   Default value for the ``--no-archive`` option.

   .. seealso:: :func:`walrus._get_do_archive_option`

.. data:: walrus.__walrus_archive_path__
   :type: str

   Default value for the ``--archive-path`` option.

   .. seealso:: :func:`walrus._get_archive_path_option`

.. data:: walrus.__walrus_source_version__
   :type: str

   Default value for the ``--source-version`` option.

   .. seealso:: :func:`walrus._get_source_version_option`

.. data:: walrus.__walrus_linesep__
   :type: Literal[\'LF\', \'CRLF\', \'CR\', \'auto detect\']

   Default value for the ``--linesep`` option.

   .. seealso:: :func:`walrus._get_linesep_option`

.. data:: walrus.__walrus_indentation__
   :type: str

   Default value for the ``--indentation`` option.

   .. seealso:: :func:`walrus._get_indentation_option`

.. data:: walrus.__walrus_pep8__
   :type: Literal[\'will conform to PEP 8\', \'will not conform to PEP 8\']

   Default value for the ``--no-pep8`` option.

   .. seealso:: :func:`walrus._get_pep8_option`
