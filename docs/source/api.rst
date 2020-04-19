API Reference
=============

.. module:: walrus

.. .. automodule:: walrus
..    :members:
..    :undoc-members:
..    :show-inheritance:

Public Interface
----------------

.. autofunction:: walrus.main

.. autofunction:: walrus.walrus

.. autofunction:: walrus.convert

Conversion Implementation
-------------------------

The main logic of the :mod:`walrus` conversion is to wrap *assignment expressions*
as functions which manipulates variable namespaces to implement the **assignment**
part and evaluates original code blocks to archive the **expression** part.

For conversion algorithms and details, please refer to :doc:`concept`.

Data Structures
~~~~~~~~~~~~~~~

During conversion, we utilised :class:`bpc_utils.Config` to store and deliver the
configurations over the conversion :class:`~walrus.Context` instances, which should
be as following:

.. class:: Config

   Configuration object shared over the conversion process of a single source file.

   .. attribute:: indentation
      :type: str

      indentation sequence

   .. attribute:: linesep
      :type: Union[Literal['\n'], Literal['\r\n'], Literal['\r']]

      line seperator

   .. attribute:: pep8
      :type: bool

      :pep:`8` compliant conversion flag

Since conversion of assignment expressions in different statements has different
processing logics and templates, we hereby describe two data structures representing
such information.

The :class:`Function` represents an assignment expression at most circumstances. It
will be provided to :data:`~walrus.FUNC_TEMPLATE` to render the wrapper function for
the conversion.

.. class:: Function

   :bases: :class:`typing.TypedDict`

   .. attribute:: name
      :type: str

      Function name, as the original *left-hand-side* variable name
      from assignment expression.

   .. attribute:: uuid
      :type: str

      UUID text in the function name to avoid renaming existing functions.

   .. attribute:: keyword
      :type: Union[Literal['global'], Literal['nonlocal']]

      Scope manipulation keyword. If :attr:`name` is declared in *global*
      namespace, then it will be ``'global'``, else ``'nonlocal'``.

      .. note::
         If the *left-hand-side* variable name is recorded in the global context
         (:attr:`Context.global_stmt`), then the converted function should use
         ``'global'`` as keyword.

The :class:`Lambda` represents an assignment expression declared in *lambda*
statements. It will be provided to :data:`~walrus.LAMBDA_FUNC_TEMPLATE` to render
the wrapper function for the conversion.

.. class:: Lambda

   :bases: :class:`typing.TypedDict`

   .. attribute:: param
      :type: str

      Concatenated parameter string for the wrapper function.

   .. attribute:: suite
      :type: str

      Original *lambda* suite with assignment expressions converted.

   .. attribute:: uuid
      :type: str

      UUID text in the function name to avoid renaming existing functions.

Conversion Templates
~~~~~~~~~~~~~~~~~~~~

For general conversion scenarios, the converted wrapper functions will
render based on the following templates.

.. data:: NAME_TEMPLATE
   :type: List[str]

   .. code:: python

      ['if False:',
       '%(indentation)s%(name_list)s = NotImplemented']

   Declares variables in the current scope for using ``global`` and/or
   ``nonlocal`` statements.

   :Variables:
      * **indentation** -- indentation sequence as defined in
        :attr:`Config.indentation <walrus.Config.indentation>`
      * **name_list** -- equal (``=``) seperated list of variable names

   .. important::

      This is a rather hack way to fool the Python interpreter that such
      variables had been declared in the current scope, whilst not actually
      declaring such variables at runtime.

.. data:: CALL_TEMPLATE
   :type: str

   .. code:: python

      '__walrus_wrapper_%(name)s_%(uuid)s(%(expr)s)'

   Wrapper function call to replace the original assignment expression.

   :Variables:
      * **name** -- *left-hand-side* variable name
      * **uuid** -- UUID text
      * **expr** -- *right-hand-side* expression

.. data:: FUNC_TEMPLATE
   :type: List[str]

   .. code:: python

      ['def __walrus_wrapper_%(name)s_%(uuid)s(expr):',
       '%(indentation)s"""Wrapper function for assignment expression."""',
       '%(indentation)s%(keyword)s %(name)s',
       '%(indentation)s%(name)s = expr',
       '%(indentation)sreturn %(name)s']

   Wrapper function call to replace the original assignment expression.

   :Variables:
      * **indentation** -- indentation sequence as defined in
        :attr:`Config.indentation <walrus.Config.indentation>`
      * \*\*\ **kwargs** -- function record as described in :class:`Function`

For assignment expression in *lambda* statements, the converted wrapper
function will render based on the following templates.

.. data:: LAMBDA_CALL_TEMPLATE
   :type: str

   .. code:: python

      '__walrus_wrapper_lambda_%(uuid)s'

   Wrapper function call to replace the original assignment expression.

   :Variables:
      * **uuid** -- UUID text

.. data:: LAMBDA_FUNC_TEMPLATE
   :type: List[str]

   .. code:: python

      ['def __walrus_wrapper_lambda_%(uuid)s(%(param)s):',
       '%(indentation)s"""Wrapper function for lambda definitions."""',
       '%(indentation)s%(suite)s']

   Wrapper function call to replace the original assignment expression.

   :Variables:
      * **indentation** -- indentation sequence as defined in
        :attr:`Config.indentation <walrus.Config.indentation>`
      * \*\*\ **kwargs** -- function record as described in :class:`Lambda`

For assignment expression in *class variables* (``ClassVar``), the converted
wrapper function will render based on the following templates.

.. data:: LCL_DICT_TEMPLATE
   :type: str

   .. code:: python

      '_walrus_wrapper_%(cls)s_dict = dict()'

   Dictionary for recording decalred class variables.

   :Variables:
      * **cls** -- class name

.. data:: LCL_NAME_TEMPLATE
   :type: str

   .. code:: python

      '_walrus_wrapper_%(cls)s_dict[%(name)r]'

   Record regular assign expressions to the local dictionary.

   :Variables:
      * **cls** -- class name
      * **name** -- variable name

.. data:: LCL_CALL_TEMPLATE
   :type: str

   .. code:: python

      '__WalrusWrapper%(cls)s.get_%(name)s_%(uuid)s()'

   Fetch variable recorded in the local dictionary.

   :Variables:
      * **cls** -- class name
      * **name** -- variable name
      * **uuid** -- UUID text

.. data:: LCL_VARS_TEMPLATE
   :type: str

   .. code:: python

      ['[setattr(%(cls)s, k, v) for k, v in _walrus_wrapper_%(cls)s_dict.items()]',
       'del _walrus_wrapper_%(cls)s_dict']

   Assign variables recorded in the local dictionary back to the class namespace.

   :Variables:
      * **cls** -- class name

.. data:: CLS_CALL_TEMPLATE
   :type: str

   .. code:: python

      '__WalrusWrapper%(cls)s.set_%(name)s_%(uuid)s(%(expr)s)'

   Record variable in the local dictionary.

   :Variables:
      * **cls** -- class name
      * **name** -- variable name
      * **uuid** -- UUID text
      * **expr** -- original *right-hand-side* expression

.. data:: CLS_NAME_TEMPLATE
   :type: str

   .. code:: python

      ['class __WalrusWrapper%(cls)s:',
       '%(indentation)s"""Wrapper class for assignment expression."""']

   Wrapper class definition.

   :Variables:
      * **cls** -- class name
      * **indentation** -- indentation sequence as defined in
        :attr:`Config.indentation <walrus.Config.indentation>`

.. data:: CLS_FUNC_TEMPLATE
   :type: str

   .. code:: python

      ['%(indentation)s@staticmethod',
       '%(indentation)sdef set_%(name)s_%(uuid)s(expr):',
       '%(indentation)s%(indentation)s"""Wrapper function for assignment expression."""',
       '%(indentation)s%(indentation)s_walrus_wrapper_%(cls)s_dict[%(name)r] = expr',
       '%(indentation)s%(indentation)sreturn _walrus_wrapper_%(cls)s_dict[%(name)r]',
       '',
       '%(indentation)s@staticmethod',
       '%(indentation)sdef get_%(name)s_%(uuid)s():',
       '%(indentation)s%(indentation)s"""Wrapper function for assignment expression."""',
       '%(indentation)s%(indentation)sif %(name)r in _walrus_wrapper_%(cls)s_dict:',
       '%(indentation)s%(indentation)s%(indentation)sreturn _walrus_wrapper_%(cls)s_dict[%(name)r]',
       "%(indentation)s%(indentation)sraise NameError('name %%r is not defined' %% %(name)r)"]

   Classmethods for getting and setting variables from the wrapper class context.

   :Variables:
      * **indentation** -- indentation sequence as defined in
        :attr:`Config.indentation <walrus.Config.indentation>`
      * **cls** -- class name
      * \*\*\ **kwargs** -- function record as described in :class:`Function`

Conversion Contexts
~~~~~~~~~~~~~~~~~~~

.. autoclass:: walrus.Context
   :members:
   :undoc-members:
   :private-members:

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

Internal Auxiliaries
--------------------

Options & Defaults
~~~~~~~~~~~~~~~~~~

.. autodata:: walrus.WALRUS_VERSIONS

Below are option getter utility functions. Option value precedence is::

   explicit value (CLI/API arguments) > environment variable > default value

.. autofunction:: walrus._get_quiet_option
.. autofunction:: walrus._get_do_archive_option
.. autofunction:: walrus._get_archive_path_option
.. autofunction:: walrus._get_source_version_option
.. autofunction:: walrus._get_linesep_option
.. autofunction:: walrus._get_indentation_option
.. autofunction:: walrus._get_pep8_option

The following variables are used for fallback default values of options.

.. autodata:: walrus._default_quiet
.. autodata:: walrus._default_do_archive
.. autodata:: walrus._default_archive_path
.. autodata:: walrus._default_source_version
.. autodata:: walrus._default_linesep
.. autodata:: walrus._default_indentation
.. autodata:: walrus._default_pep8

.. important::

   For :data:`_default_linesep` and :data:`_default_indentation`,
   :data:`None` means *auto detection* during runtime.

CLI Utilities
~~~~~~~~~~~~~

.. autofunction:: walrus.get_parser

The following variables are used for help messages in the argument parser.

.. data:: walrus.__cwd__
   :type: str

   Current working directory returned by :func:`os.getcwd`.

.. data:: walrus.__walrus_quiet__
   :type: Union[Literal['quiet mode'], Literal['non-quiet mode']]

   Default value for the ``--quiet`` option.

   .. seealso:: :func:`walrus._get_quiet_option`

.. data:: walrus.__walrus_concurrency__
   :type: Union[int, Literal['auto detect']]

   Default value for the ``--concurrency`` option.

   .. seealso:: :func:`walrus._get_concurrency_option`

.. data:: walrus.__walrus_do_archive__
   :type: Union[Literal['will do archive'], Literal['will not do archive']]

   Default value for the ``--no-archive`` option.

   .. seealso:: :func:`_get_do_archive_option`

.. data:: walrus.__walrus_archive_path__
   :type: str

   Default value for the ``--archive-path`` option.

   .. seealso:: :func:`walrus._get_archive_path_option`

.. data:: walrus.__walrus_source_version__
   :type: str

   Default value for the ``--source-version`` option.

   .. seealso:: :func:`walrus._get_source_version_option`

.. data:: walrus.__walrus_linesep__
   :type: Union[Literal['LF'], Literal['CRLF'], Literal['CR'], Literal['auto detect']]

   Default value for the ``--linesep`` option.

   .. seealso:: :func:`walrus._get_linesep_option`

.. data:: walrus.__walrus_indentation__
   :type: str

   Default value for the ``--indentation`` option.

   .. seealso:: :func:`walrus._get_indentation_option`

.. data:: walrus.__walrus_pep8__
   :type: Union[Literal['will conform to PEP 8'], Literal['will not conform to PEP 8']]

   Default value for the ``--no-pep8`` option.

   .. seealso:: :func:`walrus._get_pep8_option`
