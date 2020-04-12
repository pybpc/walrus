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

.. For implementation algorithms and details, please refer to :doc:`...`.

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
      * **name_list** -- comma-seperated list of variable names

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

   .. attribute:: config
      :type: Config

      Internal configurations as described in :class:`Config`.

   .. attribute:: _indentation
      :type: str

      Indentation sequence.

   .. attribute:: _linesep
      :type: Union[Literal['\n'], Literal['\r\n'], Literal['\r']]

      Line seperator.

   .. attribute:: _pep8
      :type: bool

      :pep:`8` compliant conversion flag.

   .. attribute:: _root
      :type: parso.tree.NodeOrLeaf

      Root node as the ``node`` parameter.

   .. attribute:: _column
      :type: int

      Current indentation level.

   .. attribute:: _keyword
      :type: Union[Literal['global'], Literal['nonlocal']]

      The ``global`` / ``nonlocal`` keyword.

   .. attribute:: _context
      :type: List[str]

      Variable names in ``global`` statements.

   .. attribute:: _prefix_or_suffix
      :type: bool

      Flag if buffer is now :attr:`self._prefix <walrus.Context._prefix>`.

   .. attribute:: _node_before_walrus
      :type: Optional[parso.tree.NodeOrLeaf]

      Preceding node with assignment expression, i.e. the *insersion point*.

   .. attribute:: _prefix
      :type: str

      Codes before insersion point.

   .. attribute:: _suffix
      :type: str

      Codes after insersion point.

   .. attribute:: _buffer
      :type: str

      Final converted result.

   .. attribute:: _vars
      :type: List[str]

      Variable declaration blocks rendered from :data:`~walrus.NAME_TEMPLATE`.

   .. attribute:: _func
      :type: List[Function]

      Converted wrapper functions described as :class:`Function`.

   .. attribute:: _lamb
      :type: List[Lambda]

      Converted *lambda* statements described as :class:`Lambda`.

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

CLI Utilities
-------------

.. autofunction:: walrus.get_parser

The following variables are used for help messages in the argument parser.

.. data:: walrus.__cwd__
   :type: str

   Current working directory returned by :func:`os.getcwd`.

.. data:: walrus.__walrus_archive_path__
   :type: str

   Path to archive original source code.

   .. seealso:: :func:`walrus._get_archive_path_option`

.. data:: walrus.__walrus_source_version__
   :type: str

   Parse source code as Python version.

   .. seealso:: :func:`walrus._get_source_version_option`

.. data:: walrus.__walrus_linesep__
   :type: Union[Literal['\n'], Literal['\r\n'], Literal['\r'], Literal['auto detect']]

   Line separator (``LF``, ``CRLF``, ``CR``) to read source files.

   .. seealso:: :func:`walrus._get_linesep_option`

.. data:: walrus.__walrus_indentation__
   :type: Union[int, Literal['\t'], Literal['auto detect']]

   Code indentation style; an integer for the number of spaces,
   or ``\t`` for tabs.
