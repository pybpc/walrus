# -*- coding: utf-8 -*-
"""Back-port compiler for Python 3.8 assignment expressions."""

import argparse
import io
import os
import pathlib
import re
import sys
import traceback

import parso
import tbtrim
from bpc_utils import (BPCSyntaxError, Config, TaskLock, UUID4Generator, archive_files,
                       detect_encoding, detect_files, detect_indentation, detect_linesep,
                       first_non_none, get_parso_grammar_versions, map_tasks, parse_boolean_state,
                       parse_indentation, parse_linesep, parse_positive_integer, parso_parse,
                       recover_files)

__all__ = ['main', 'walrus', 'convert']

# version string
__version__ = '0.1.4'

###############################################################################
# Auxiliaries

#: Get supported source versions.
#:
#: .. seealso:: :func:`bpc_utils.get_parso_grammar_versions`
WALRUS_SOURCE_VERSIONS = get_parso_grammar_versions(minimum='3.8')

# will be set in every call to `convert()`
uuid_gen = None  # TODO: will be refactored into the Context class

# option default values
#: Default value for the ``quiet`` option.
_default_quiet = False
#: Default value for the ``concurrency`` option.
_default_concurrency = None  # auto detect
#: Default value for the ``do_archive`` option.
_default_do_archive = True
#: Default value for the ``archive_path`` option.
_default_archive_path = 'archive'
#: Default value for the ``source_version`` option.
_default_source_version = WALRUS_SOURCE_VERSIONS[-1]
#: Default value for the ``linesep`` option.
_default_linesep = None  # auto detect
#: Default value for the ``indentation`` option.
_default_indentation = None  # auto detect
#: Default value for the ``pep8`` option.
_default_pep8 = True

# option getter utility functions
# option value precedence is: explicit value (CLI/API arguments) > environment variable > default value


def _get_quiet_option(explicit=None):
    """Get the value for the ``quiet`` option.

    Args:
        explicit (Optional[bool]): the value explicitly specified by user,
            :data:`None` if not specified

    Returns:
        bool: the value for the ``quiet`` option

    :Environment Variables:
        :envvar:`WALRUS_QUIET` -- the value in environment variable

    See Also:
        :data:`_default_quiet`

    """
    # We need lazy evaluation, so first_non_none(a, b, c) does not work here
    # with PEP 505 we can simply write a ?? b ?? c
    def _option_layers():
        yield explicit
        yield parse_boolean_state(os.getenv('WALRUS_QUIET'))
        yield _default_quiet
    return first_non_none(_option_layers())


def _get_concurrency_option(explicit=None):
    """Get the value for the ``concurrency`` option.

    Args:
        explicit (Optional[int]): the value explicitly specified by user,
            :data:`None` if not specified

    Returns:
        Optional[int]: the value for the ``concurrency`` option;
        :data:`None` means *auto detection* at runtime

    :Environment Variables:
        :envvar:`WALRUS_CONCURRENCY` -- the value in environment variable

    See Also:
        :data:`_default_concurrency`

    """
    return parse_positive_integer(explicit or os.getenv('WALRUS_CONCURRENCY') or _default_concurrency)


def _get_do_archive_option(explicit=None):
    """Get the value for the ``do_archive`` option.

    Args:
        explicit (Optional[bool]): the value explicitly specified by user,
            :data:`None` if not specified

    Returns:
        bool: the value for the ``do_archive`` option

    :Environment Variables:
        :envvar:`WALRUS_DO_ARCHIVE` -- the value in environment variable

    See Also:
        :data:`_default_do_archive`

    """
    def _option_layers():
        yield explicit
        yield parse_boolean_state(os.getenv('WALRUS_DO_ARCHIVE'))
        yield _default_do_archive
    return first_non_none(_option_layers())


def _get_archive_path_option(explicit=None):
    """Get the value for the ``archive_path`` option.

    Args:
        explicit (Optional[str]): the value explicitly specified by user,
            :data:`None` if not specified

    Returns:
        str: the value for the ``archive_path`` option

    :Environment Variables:
        :envvar:`WALRUS_ARCHIVE_PATH` -- the value in environment variable

    See Also:
        :data:`_default_archive_path`

    """
    return explicit or os.getenv('WALRUS_ARCHIVE_PATH') or _default_archive_path


def _get_source_version_option(explicit=None):
    """Get the value for the ``source_version`` option.

    Args:
        explicit (Optional[str]): the value explicitly specified by user,
            :data:`None` if not specified

    Returns:
        str: the value for the ``source_version`` option

    :Environment Variables:
        :envvar:`WALRUS_SOURCE_VERSION` -- the value in environment variable

    See Also:
        :data:`_default_source_version`

    """
    return explicit or os.getenv('WALRUS_SOURCE_VERSION') or _default_source_version


def _get_linesep_option(explicit=None):
    r"""Get the value for the ``linesep`` option.

    Args:
        explicit (Optional[str]): the value explicitly specified by user,
            :data:`None` if not specified

    Returns:
        Optional[Literal['\\n', '\\r\\n', '\\r']]: the value for the ``linesep`` option;
        :data:`None` means *auto detection* at runtime

    :Environment Variables:
        :envvar:`WALRUS_LINESEP` -- the value in environment variable

    See Also:
        :data:`_default_linesep`

    """
    return parse_linesep(explicit or os.getenv('WALRUS_LINESEP') or _default_linesep)


def _get_indentation_option(explicit=None):
    """Get the value for the ``indentation`` option.

    Args:
        explicit (Optional[Union[str, int]]): the value explicitly specified by user,
            :data:`None` if not specified

    Returns:
        Optional[str]: the value for the ``indentation`` option;
        :data:`None` means *auto detection* at runtime

    :Environment Variables:
        :envvar:`WALRUS_INDENTATION` -- the value in environment variable

    See Also:
        :data:`_default_indentation`

    """
    return parse_indentation(explicit or os.getenv('WALRUS_INDENTATION') or _default_indentation)


def _get_pep8_option(explicit=None):
    """Get the value for the ``pep8`` option.

    Args:
        explicit (Optional[bool]): the value explicitly specified by user,
            :data:`None` if not specified

    Returns:
        bool: the value for the ``pep8`` option

    :Environment Variables:
        :envvar:`WALRUS_PEP8` -- the value in environment variable

    See Also:
        :data:`_default_pep8`

    """
    def _option_layers():
        yield explicit
        yield parse_boolean_state(os.getenv('WALRUS_PEP8'))
        yield _default_pep8
    return first_non_none(_option_layers())


###############################################################################
# Traceback Trimming (tbtrim)

# root path
ROOT = pathlib.Path(__file__).resolve().parent


def predicate(filename):
    return pathlib.Path(filename).parent == ROOT


tbtrim.set_trim_rule(predicate, strict=True, target=BPCSyntaxError)

###############################################################################
# Main Conversion Implementation

# walrus wrapper template
NAME_TEMPLATE = '''\
if False:
%(indentation)s%(name_list)s = NotImplemented
'''.splitlines()  # `str.splitlines` will remove trailing newline
CALL_TEMPLATE = '__walrus_wrapper_%(name)s_%(uuid)s(%(expr)s)'
FUNC_TEMPLATE = '''\
def __walrus_wrapper_%(name)s_%(uuid)s(expr):
%(indentation)s"""Wrapper function for assignment expression."""
%(indentation)s%(keyword)s %(name)s
%(indentation)s%(name)s = expr
%(indentation)sreturn %(name)s
'''.splitlines()  # `str.splitlines` will remove trailing newline

# special template for lambda
LAMBDA_CALL_TEMPLATE = '__walrus_wrapper_lambda_%(uuid)s'
LAMBDA_FUNC_TEMPLATE = '''\
def __walrus_wrapper_lambda_%(uuid)s(%(param)s):
%(indentation)s"""Wrapper function for lambda definitions."""
%(indentation)s%(suite)s
'''.splitlines()  # `str.splitlines` will remove trailing newline

# special templates for ClassVar
# locals dict
LCL_DICT_TEMPLATE = '_walrus_wrapper_%(cls)s_dict = dict()'
LCL_NAME_TEMPLATE = '_walrus_wrapper_%(cls)s_dict[%(name)r]'
LCL_CALL_TEMPLATE = '__WalrusWrapper%(cls)s.get(%(name)r)'
LCL_VARS_TEMPLATE = '''\
[setattr(%(cls)s, k, v) for k, v in _walrus_wrapper_%(cls)s_dict.items()]
del _walrus_wrapper_%(cls)s_dict
'''.splitlines()  # `str.splitlines` will remove trailing newline
# class clause
CLS_CALL_TEMPLATE = '__WalrusWrapper%(cls)s.set(%(name)r, %(expr)s)'
CLS_NAME_TEMPLATE = '''\
class __WalrusWrapper%(cls)s:
%(indentation)s"""Wrapper class for assignment expression."""
'''.splitlines()  # `str.splitlines` will remove trailing newline
CLS_SET_FUNC_TEMPLATE = '''\
%(indentation)s@staticmethod
%(indentation)sdef set(name, expr):
%(indentation)s%(indentation)s"""Wrapper function for assignment expression."""
%(indentation)s%(indentation)s_walrus_wrapper_%(cls)s_dict[name] = expr
%(indentation)s%(indentation)sreturn _walrus_wrapper_%(cls)s_dict[name]
'''.splitlines()  # `str.splitlines` will remove trailing newline
CLS_GET_FUNC_TEMPLATE = '''\
%(indentation)s@staticmethod
%(indentation)sdef get(name):
%(indentation)s%(indentation)s"""Wrapper function for assignment expression."""
%(indentation)s%(indentation)sif name in _walrus_wrapper_%(cls)s_dict:
%(indentation)s%(indentation)s%(indentation)sreturn _walrus_wrapper_%(cls)s_dict[name]
%(indentation)s%(indentation)sraise NameError('name %%r is not defined' %% name)
'''.splitlines()  # `str.splitlines` will remove trailing newline
CLS_EXT_CALL_TEMPLATE = '__WalrusWrapper%(cls)s.ext_%(name)s_%(uuid)s(%(expr)s)'
CLS_EXT_VARS_GLOBAL_TEMPLATE = '%(indentation)sglobal %(name_list)s'
CLS_EXT_VARS_NONLOCAL_TEMPLATE = '%(indentation)snonlocal %(name_list)s'
CLS_EXT_FUNC_TEMPLATE = '''\
%(indentation)s@staticmethod
%(indentation)sdef ext_%(name)s_%(uuid)s(expr):
%(indentation)s%(indentation)s"""Wrapper function for assignment expression."""
%(indentation)s%(indentation)s%(keyword)s %(name)s
%(indentation)s%(indentation)s%(name)s = expr
%(indentation)s%(indentation)sreturn %(name)s
'''.splitlines()  # `str.splitlines` will remove trailing newline

class Context:
    """General conversion context.

    Args:
        node (parso.tree.NodeOrLeaf): parso AST
        config (Config): conversion configurations

    Keyword Args:
        column (int): current indentation level
        keyword (Optional[Literal['global', 'nonlocal']]): keyword for wrapper function
        context (Optional[List[str]]): global context (:term:`namespace`)
        raw (bool): raw processing flag

    Important:
        ``raw`` should be :data:`True` only if the ``node`` is in the clause of another *context*,
        where the converted wrapper functions should be inserted.

        Typically, only if ``node`` is an assignment expression (:token:`namedexpr_test`) node,
        ``raw`` will be set as :data:`True`, in consideration of nesting assignment expressions.

    """

    @property
    def string(self):
        """Conversion buffer (:attr:`self._buffer <walrus.Context._buffer>`).

        :rtype: str

        """
        return self._buffer

    @property
    def lambdef(self):
        """Lambda definitions (:attr:`self._lamb <walrus.Context._lamb>`).

        :rtype: List[Lambda]

        """
        return self._lamb

    @property
    def variables(self):
        """Assignment expression variable records (:attr:`self._vars <walrus.Context._vars>`).

        The variables are the *left-hand-side* variable name of the assignment expressions.

        :rtype: List[str]

        """
        return self._vars

    @property
    def functions(self):
        """Assignment expression wrapper function records (:attr:`self._func <walrus.ontext._func>`).

        :rtype: List[Function]

        """
        return self._func

    @property
    def global_stmt(self):
        """List of variables declared in the :token:`global <global_stmt>` statements.

        If current root node (:attr:`self._root <walrus.Context._root>`) is a function definition
        (:class:`parso.python.tree.Function`), then returns an empty list; else returns
        :attr:`self._context <walrus.Context._context>`.

        :rtype: List[str]

        """
        if self._root.type == 'funcdef':
            return list()
        return self._context

    def __init__(self, node, config, *, column=0, keyword=None, context=None, raw=False):
        if keyword is None:
            keyword = self.guess_keyword(node)
        if context is None:
            context = list()

        #: Config: Internal configurations as described in :class:`Config`
        self.config = config
        #: str: Indentation sequence.
        self._indentation = config.indentation
        #: Literal['\\n', '\\r\\n', '\\r']: Line seperator.
        self._linesep = config.linesep

        #: bool: :pep:`8` compliant conversion flag.
        self._pep8 = config.pep8

        #: parso.tree.NodeOrLeaf: Root node as the ``node`` parameter.
        self._root = node
        #: int: Current indentation level.
        self._column = column
        #: Literal['global', 'nonlocal']:
        #: The :token:`global <global_stmt>` / :token:`nonlocal <nonlocal_stmt>` keyword.
        self._keyword = keyword
        #: List[str]: Variable names in :token:`global <global_stmt>` statements.
        self._context = list(context)

        #: bool: Flag if buffer is now :attr:`self._prefix <walrus.Context._prefix>`.
        self._prefix_or_suffix = True
        #: Optional[parso.tree.NodeOrLeaf]: Preceding node with assignment expression, i.e. the *insersion point*.
        self._node_before_walrus = None

        #: str: Codes before insersion point.
        self._prefix = ''
        #: str: Codes after insersion point.
        self._suffix = ''
        #: str: Final converted result.
        self._buffer = ''

        #: List[str]: Original *left-hand-side* variable names in assignment expressions.
        self._vars = list()
        #: List[Lambda]: Converted *lambda* statements described as :class:`Lambda`.
        self._lamb = list()
        #: List[Function]: Converted wrapper functions described as :class:`Function`.
        self._func = list()

        self._walk(node)  # traverse children
        if raw:
            self._buffer = self._prefix + self._suffix
        else:
            self._concat()  # generate final result

    def __iadd__(self, code):
        """Support of ``+=`` operator.

        If :attr:`self._prefix_or_suffix <walrus.Context._prefix_or_suffix>` is :data:`True`, then
        the ``code`` will be appended to :attr:`self._prefix <walrus.Context._prefix>`; else
        it will be appended to :attr:`self._suffix <walrus.Context._suffix>`.

        Args:
            code (str): code string

        """
        if self._prefix_or_suffix:
            self._prefix += code
        else:
            self._suffix += code
        return self

    def __str__(self):
        """Returns *stripped* :attr:`self._buffer <walrus.Context._buffer>`."""
        return self._buffer.strip()

    def _walk(self, node):
        """Start traversing the AST module.

        Args:
            node (parso.tree.NodeOrLeaf): parso AST

        The method traverses through all *children* of ``node``. It first checks
        if such child has assignment expression. If so, it will toggle
        :attr:`self._prefix_or_suffix <walrus.Context._prefix_or_suffix>` as
        :data:`False` and save the last previous child as
        :attr:`self._node_before_walrus <walrus.Context._node_before_walrus>`.
        Then it processes the child with :meth:`self._process <walrus.Context._process>`.

        """
        # process node
        if hasattr(node, 'children'):
            last_node = None
            for child in node.children:
                if self.has_walrus(child):
                    self._prefix_or_suffix = False
                    self._node_before_walrus = last_node
                self._process(child)
                last_node = child
            return

        # process leaf
        self += node.get_code()

    def _process(self, node):
        """Walk parso AST.

        Args:
            node (parso.tree.NodeOrLeaf): parso AST

        All processing methods for a specific ``node`` type are defined as
        ``_process_{type}``. This method first checks if such processing
        method exists. If so, it will call such method on the ``node``;
        else it will traverse through all *children* of ``node``, and perform
        the same logic on each child.

        See Also:
            * :token:`suite`

              - :meth:`Context._process_suite_node`
              - :meth:`ClassContext._process_suite_node`

            * :token:`namedexpr_test`

              - :meth:`Context._process_namedexpr_test`
              - :meth:`ClassContext._process_namedexpr_test`

            * :token:`global_stmt`

              - :meth:`Context._process_global_stmt`
              - :meth:`ClassContext._process_global_stmt`

            * :token:`classdef`

              - :meth:`Context._process_classdef`

            * :token:`funcdef`

              - :meth:`Context._process_funcdef`

            * :token:`lambdef`

              - :meth:`Context._process_lambdef`

            * :token:`if_stmt`

              - :meth:`Context._process_if_stmt`

            * :token:`while_stmt`

              - :meth:`Context._process_while_stmt`

            * :token:`for_stmt`

              - :meth:`Context._process_for_stmt`

            * :token:`with_stmt`

              - :meth:`Context._process_with_stmt`

            * :token:`try_stmt`

              - :meth:`Context._process_try_stmt`

            * :token:`argument`

              - :meth:`Context._process_argument`

            * :token:`name`

              - :meth:`ClassContext._process_name`
              - :meth:`ClassContext._process_defined_name`

            * :token:`nonlocal_stmt`

              - :meth:`ClassContext._process_nonlocal_stmt`

        """
        func_name = '_process_%s' % node.type
        if hasattr(self, func_name):
            func = getattr(self, func_name)
            func(node)
            return

        if hasattr(node, 'children'):
            for child in node.children:
                func_name = '_process_%s' % child.type
                func = getattr(self, func_name, self._process)
                func(child)
            return

        # leaf node
        self += node.get_code()

    def _process_suite_node(self, node, func=False, raw=False, cls_ctx=None):
        """Process indented suite (:token:`suite` or others).

        Args:
            node (parso.tree.NodeOrLeaf): suite node
            func (bool): if ``node`` is suite from function definition
            raw (bool): raw processing flag
            cls_ctx (Optional[str]): class name if ``node`` is in class context

        This method first checks if ``node`` contains assignment expression.
        If not, it will not perform any processing, rather just append the
        original source code to context buffer.

        If ``node`` contains assignment expression, then it will initiate another
        :class:`Context` instance to perform the conversion process on such
        ``node``; whilst if ``cls_ctx`` is provided, then it will initiate a
        :class:`ClassContext` instance instead.

        Note:
            If ``func`` is True, when initiating the :class:`Context` instance,
            ``keyword`` will be set as ``'nonlocal'``, as in the wrapper function
            it will refer the original *left-hand-side* variable from the outer
            function scope rather than global namespace.

        The method will keep *global* statements (:meth:`Context.global_stmt`)
        from the temporary :class:`Context` (or :class:`ClassContext`) instance in the
        current instance.

        And if ``raw`` is set as :data:`True`, the method will keep records of converted wrapper
        functions (:meth:`Context.functions`), converted *lambda* statements (:meth:`Context.lambdef`)
        and *left-hand-side* variable names (:meth:`Context.variables`) into current instance as well.

        Important:
            ``raw`` should be :data:`True` only if the ``node`` is in the clause of another *context*,
            where the converted wrapper functions should be inserted.

            However, it seems useless in current implementation.

        """
        if not self.has_walrus(node):
            self += node.get_code()
            return

        indent = self._column + 1
        self += self._linesep + self._indentation * indent

        if func:
            keyword = 'nonlocal'
        else:
            keyword = self._keyword

        # process suite
        if cls_ctx is None:
            ctx = Context(node=node, config=self.config,
                          context=self._context, column=indent,
                          keyword=keyword, raw=raw)
        else:
            ctx = ClassContext(cls_ctx=cls_ctx,
                               node=node, config=self.config,
                               context=self._context, column=indent,
                               keyword=keyword, raw=raw)
        self += ctx.string.lstrip()

        # keep records
        if raw:
            self._lamb.extend(ctx.lambdef)
            self._vars.extend(ctx.variables)
            self._func.extend(ctx.functions)
        self._context.extend(ctx.global_stmt)

    def _process_namedexpr_test(self, node):
        """Process assignment expression (:token:`namedexpr_test`).

        Args:
            node (parso.python.tree.PythonNode): assignment expression node

        This method converts the assignment expression into wrapper function
        and extracts related records for inserting converted codes.

        * The *left-hand-side* variable name will be recorded in
          :attr:`self._vars <walrus.Context._vars>`.
        * The *right-hand-side* expression will be converted using another
          :class:`Context` instance and replaced with a wrapper function call
          rendered from :data:`CALL_TEMPLATE`; information described as
          :class:`Function` will be recorded into :attr:`self._func <walrus.Context._func>`.

        """
        # split assignment expression
        node_name, _, node_expr = node.children
        name = node_name.value
        nuid = uuid_gen.gen()

        # calculate expression string
        ctx = Context(node=node_expr, config=self.config,
                      context=self._context, column=self._column,
                      keyword=self._keyword, raw=True)
        expr = ctx.string.strip()
        self._vars.extend(ctx.variables)
        self._func.extend(ctx.functions)

        # replacing codes
        code = CALL_TEMPLATE % dict(name=name, uuid=nuid, expr=expr)
        prefix, suffix = self.extract_whitespaces(node)
        self += prefix + code + suffix

        self._context.extend(ctx.global_stmt)
        if name in self._context:
            keyword = 'global'
        else:
            keyword = self._keyword

        # keep records
        self._vars.append(name)
        self._func.append(dict(name=name, uuid=nuid, keyword=keyword))

    def _process_global_stmt(self, node):
        """Process function definition (:token:`global_stmt`).

        Args:
            node (parso.python.tree.GlobalStmt): global statement node

        This method records all variables declared in a *global* statement
        into :attr:`self._context <walrus.Context._context>`.

        """
        children = iter(node.children)

        # <Keyword: global>
        next(children)
        # <Name: ...>
        name = next(children)
        self._context.append(name.value)

        while True:
            try:
                # <Operator: ,>
                next(children)
            except StopIteration:
                break

            # <Name: ...>
            name = next(children)
            self._context.append(name.value)

        # process code
        self += node.get_code()

    def _process_classdef(self, node):
        """Process class definition (:token:`classdef`).

        Args:
            node (parso.python.tree.Class): class node

        This method inserts the local namespace dictionary rendered from
        :data:`LCL_DICT_TEMPLATE` before the class definition. Then it
        converts the whole class suite context with :meth:`~Context._process_suite_node`.
        Later, it appends the reassignment code block rendered from
        :data:`LCL_VARS_TEMPLATE` to put back the attributes from the temporary
        local namespace dictionary.

        """
        flag = self.has_walrus(node)
        code = node.get_code()

        # <Name: ...>
        name = node.name
        if flag:
            if self._pep8:
                buffer = self._prefix if self._prefix_or_suffix else self._suffix

                self += self._linesep * self.missing_whitespaces(prefix=buffer, suffix=code,
                                                                 blank=1, linesep=self._linesep)

            self += self._indentation * self._column \
                 + LCL_DICT_TEMPLATE % dict(cls=name.value) \
                 + self._linesep  # noqa: E127

            if self._pep8:
                blank = 2 if self._column == 0 else 1
                buffer = self._prefix if self._prefix_or_suffix else self._suffix

                self += self._linesep * self.missing_whitespaces(prefix=buffer, suffix=code,
                                                                 blank=1, linesep=self._linesep)

        # <Keyword: class>
        # <Name: ...>
        # [<Operator: (>, PythonNode(arglist, [...]]), <Operator: )>]
        # <Operator: :>
        for child in node.children[:-1]:
            self._process(child)

        # PythonNode(suite, [...]) / PythonNode(simple_stmt, [...])
        suite = node.children[-1]
        self._process_suite_node(suite, cls_ctx=name.value)

        if flag:
            indent = self._indentation * self._column

            if self._pep8:
                blank = 2 if self._column == 0 else 1
                buffer = self._prefix if self._prefix_or_suffix else self._suffix
                self += self._linesep * self.missing_whitespaces(prefix=buffer, suffix='',
                                                                 blank=blank, linesep=self._linesep)

            self += indent \
                 + ('%s%s' % (self._linesep, indent)).join(LCL_VARS_TEMPLATE) % dict(indentation=self._indentation,
                                                                                     cls=name.value) \
                 + self._linesep  # noqa: E127

            if self._pep8:
                buffer = self._prefix if self._prefix_or_suffix else self._suffix

                code = ''
                leaf = node.get_next_leaf()
                while leaf is not None:
                    code += leaf.get_code()
                    leaf = leaf.get_next_leaf()
                self += self._linesep * self.missing_whitespaces(prefix=buffer, suffix=code,
                                                                 blank=1, linesep=self._linesep)

    def _process_funcdef(self, node):
        """Process function definition (:token:`funcdef`).

        Args:
            node (parso.python.tree.Function): function node

        This method converts the function suite with
        :meth:`~Context._process_suite_node`.

        """
        # 'def' NAME '(' PARAM ')' [ '->' NAME ] ':' SUITE
        for child in node.children[:-1]:
            self._process(child)
        self._process_suite_node(node.children[-1], func=True)

    def _process_lambdef(self, node):
        """Process lambda definition (``lambdef``).

        Args:
            node (parso.python.tree.Lambda): lambda node

        This method first checks if ``node`` contains assignment expressions.
        If not, it will append the original source code directly to the buffer.

        For *lambda* statements with assignment expressions, this method
        will extract the parameter list and initiate a :class:`LambdaContext`
        instance to convert the lambda suite. Such information will be recorded
        as :class:`Lambda` in :attr:`self._lamb <Context._lamb>`.

        .. note:: For :class:`LambdaContext`, ``keyword`` should always be ``'nonlocal'``.

        Then it will replace the original lambda statement with a wrapper function
        call rendered from :data:`LAMBDA_CALL_TEMPLATE`.

        """
        if not self.has_walrus(node):
            self += node.get_code()
            return

        children = iter(node.children)

        # <Keyword: lambda>
        next(children)

        # vararglist
        para_list = list()
        for child in children:
            if child.type == 'operator' and child.value == ':':
                break
            para_list.append(child)
        param = ''.join(map(lambda n: n.get_code(), para_list))

        # test_nocond | test
        indent = self._column + 1
        ctx = LambdaContext(node=next(children), config=self.config,
                            context=self._context, column=indent,
                            keyword='nonlocal')
        suite = ctx.string.strip()

        # keep record
        nuid = uuid_gen.gen()
        self._lamb.append(dict(param=param, suite=suite, uuid=nuid))

        # replacing lambda
        self += LAMBDA_CALL_TEMPLATE % dict(uuid=nuid)

    def _process_if_stmt(self, node):
        """Process if statement (:token:`if_stmt`).

        Args:
            node (parso.python.tree.IfStmt): if node

        This method processes each indented suite under the *if*, *elif*,
        and *else* statements.

        """
        children = iter(node.children)

        # <Keyword: if>
        self._process(next(children))
        # namedexpr_test
        self._process(next(children))
        # <Operator: :>
        self._process(next(children))
        # suite
        self._process_suite_node(next(children))

        while True:
            try:
                # <Keyword: elif | else>
                key = next(children)
            except StopIteration:
                break
            self._process(key)

            if key.value == 'elif':
                # namedexpr_test
                self._process(next(children))
                # <Operator: :>
                self._process(next(children))
                # suite
                self._process_suite_node(next(children))
                continue
            if key.value == 'else':
                # <Operator: :>
                self._process(next(children))
                # suite
                self._process_suite_node(next(children))
                continue

    def _process_while_stmt(self, node):
        """Process while statement (:token:`while_stmt`).

        Args:
            node (parso.python.tree.WhileStmt): while node

        This method processes the indented suite under the *while* and optional
        *else* statements.

        """
        children = iter(node.children)

        # <Keyword: while>
        self._process(next(children))
        # namedexpr_test
        self._process(next(children))
        # <Operator: :>
        self._process(next(children))
        # suite
        self._process_suite_node(next(children))

        try:
            key = next(children)
        except StopIteration:
            return

        # <Keyword: else>
        self._process(key)
        # <Operator: :>
        self._process(next(children))
        # suite
        self._process_suite_node(next(children))

    def _process_for_stmt(self, node):
        """Process for statement (:token:`for_stmt`).

        Args:
            node (parso.python.tree.ForStmt): for node

        This method processes the indented suite under the *for* and optional
        *else* statements.

        """
        children = iter(node.children)

        # <Keyword: for>
        self._process(next(children))
        # exprlist
        self._process(next(children))
        # <Keyword: in>
        self._process(next(children))
        # testlist
        self._process(next(children))
        # <Operator: :>
        self._process(next(children))
        # suite
        self._process_suite_node(next(children))

        try:
            key = next(children)
        except StopIteration:
            return

        # <Keyword: else>
        self._process(key)
        # <Operator: :>
        self._process(next(children))
        # suite
        self._process_suite_node(next(children))

    def _process_with_stmt(self, node):
        """Process with statement (:token:`with_stmt`).

        Args:
            node (parso.python.tree.WithStmt): with node

        This method processes the indented suite under the *with* statement.

        """
        children = iter(node.children)

        # <Keyword: with>
        self._process(next(children))

        while True:
            # with_item | <Operator: ,>
            item = next(children)
            self._process(item)

            # <Operator: :>
            if item.type == 'operator' and item.value == ':':
                break

        # suite
        self._process_suite_node(next(children))

    def _process_try_stmt(self, node):
        """Process try statement (:token:`try_stmt`).

        Args:
            node (parso.python.tree.TryStmt): try node

        This method processes the indented suite under the *try*, *except*,
        *else*, and *finally* statements.

        """
        children = iter(node.children)

        while True:
            try:
                key = next(children)
            except StopIteration:
                break

            # <Keyword: try | else | finally> | PythonNode(except_clause, [...]
            self._process(key)
            # <Operator: :>
            self._process(next(children))
            # suite
            self._process_suite_node(next(children))

    def _process_argument(self, node):
        """Process function argument (:token:`argument`).

        Args:
            node (parso.python.tree.PythonNode): argument node

        This method processes arguments from function argument list.

        """
        children = iter(node.children)

        # test
        test = next(children)
        try:
            # <Operator: :=>
            op = next(children)
        except StopIteration:
            self._process(test)
            return

        if self.is_walrus(op):
            self._process_namedexpr_test(node)
            return

        # not walrus
        self._process(test)
        self._process(op)
        for child in children:
            self._process(child)

    def _concat(self):
        """Concatenate final string.

        This method tries to inserted the recorded wrapper functions and variables
        at the very location where starts to contain assignment expressions, i.e.
        between the converted codes as :attr:`self._prefix <Context._prefix>` and
        :attr:`self._suffix <Context._suffix>`.

        The inserted codes include variable declaration rendered from
        :data:`NAME_TEMPLATE`, wrapper function definitions rendered from
        :data:`FUNC_TEMPLATE` and extracted *lambda* statements rendered from
        :data:`LAMBDA_FUNC_TEMPLATE`. If :attr:`self._pep8 <Context._pep8>` is
        :data:`True`, it will insert the codes in compliance with :pep:`8`.

        """
        flag = self.has_walrus(self._root)

        # strip suffix comments
        prefix, suffix = self._strip()

        # first, the prefix codes
        self._buffer += self._prefix + prefix
        if flag and self._pep8 and self._buffer:
            if (self._node_before_walrus is not None
                    and self._node_before_walrus.type in ('funcdef', 'classdef')
                    and self._column == 0):
                blank = 2
            else:
                blank = 1
            self._buffer += self._linesep * self.missing_whitespaces(prefix=self._buffer, suffix='',
                                                                     blank=blank, linesep=self._linesep)

        # then, the variables and functions
        indent = self._indentation * self._column
        if self._pep8:
            linesep = self._linesep * (1 if self._column > 0 else 2)
        else:
            linesep = ''
        if self._vars:
            name_list = ' = '.join(sorted(set(self._vars)))
            self._buffer += indent + (
                '%s%s' % (self._linesep, indent)
            ).join(NAME_TEMPLATE) % dict(indentation=self._indentation, name_list=name_list) + self._linesep
        for func in sorted(self._func, key=lambda func: func['name']):
            if self._buffer:
                self._buffer += linesep
            self._buffer += indent + (
                '%s%s' % (self._linesep, indent)
            ).join(FUNC_TEMPLATE) % dict(indentation=self._indentation, **func) + self._linesep
        for lamb in self._lamb:
            if self._buffer:
                self._buffer += linesep
            self._buffer += indent + (
                '%s%s' % (self._linesep, indent)
            ).join(LAMBDA_FUNC_TEMPLATE) % dict(indentation=self._indentation, **lamb) + self._linesep

        # finally, the suffix codes
        if flag and self._pep8:
            blank = 2 if self._column == 0 else 1
            self._buffer += self._linesep * self.missing_whitespaces(prefix=self._buffer, suffix=suffix,
                                                                     blank=blank, linesep=self._linesep)
        self._buffer += suffix

    def _strip(self):
        """Strip comments from suffix buffer.

        Returns:
            Tuple[str, str]: a tuple of *prefix comments* and *suffix strings*

        This method separates *prefixing* comments and *suffixing* codes. It is
        rather useful when inserting codes might break `shebang`_ and encoding
        cookies (:pep:`263`), etc.

        .. _shebang: https://en.wikipedia.org/wiki/Shebang_(Unix)

        """
        prefix = ''
        suffix = ''

        lines = io.StringIO(self._suffix, newline=self._linesep)
        for line in lines:
            if line.strip().startswith('#'):
                prefix += line
                continue
            suffix += line
            break

        for line in lines:
            suffix += line
        return prefix, suffix

    @classmethod
    def has_walrus(cls, node):
        """Check if node has assignment expression. (:token:`namedexpr_test`)

        Args:
            node (parso.tree.NodeOrLeaf): parso AST

        Returns:
            bool: if ``node`` has assignment expression

        """
        if cls.is_walrus(node):
            return True
        if hasattr(node, 'children'):
            for child in node.children:
                if cls.has_walrus(child):
                    return True
        return False

    @classmethod
    def guess_keyword(cls, node):
        """Guess keyword based on node position.

        Args:
            node (parso.tree.NodeOrLeaf): parso AST

        Returns:
            Literal['global', 'nonlocal']: keyword

        This method recursively perform the following checks on the parents
        of ``node``:

        * If current ``node`` is a module (:class:`parso.python.tree.Module`),
          or a direct child of module then returns ``'global'``.
        * If the direct parrent of current ``node`` is a function
          (:class:`parso.python.tree.Function`) and/or class
          (:class:`parso.python.tree.Class`) definition, then
          returns ``'nonlocal'``.

        """
        if isinstance(node, parso.python.tree.Module):
            return 'global'

        parent = node.parent
        if isinstance(parent, parso.python.tree.Module):
            return 'global'
        if parent.type in ['funcdef', 'classdef']:
            return 'nonlocal'
        return cls.guess_keyword(parent)

    @staticmethod
    def is_walrus(node):
        """Check if ``node`` is assignment expression.

        Args:
            node (parso.tree.NodeOrLeaf): parso AST

        Returns:
            bool: if ``node`` is assignment expression

        """
        if node.type == 'namedexpr_test':
            return True
        if node.type == 'operator' and node.value == ':=':
            return True
        return False

    @staticmethod
    def missing_whitespaces(prefix, suffix, blank, linesep):
        """Count missing preceding or succeeding blank lines.

        Args:
            prefix (str): preceding source code
            suffix (str): succeeding source code
            blank (int): number of expecting blank lines
            linesep (str): line seperator

        Returns:
            int: number of preceding blank lines

        """
        count = 0
        if prefix:
            for line in reversed(prefix.split(linesep)):
                if line.strip():
                    break
                count += 1
            if count > 0:  # keep trailing newline in `prefix`
                count -= 1
        if suffix:
            for line in suffix.split(linesep):
                if line.strip():
                    break
                count += 1

        if count < 0:
            count = 0
        missing = blank - count
        if missing > 0:
            return missing
        return 0

    @staticmethod
    def extract_whitespaces(node):
        """Extract preceding and succeeding whitespaces.

        Args:
            node (parso.tree.NodeOrLeaf) parso AST

        Returns:
            Tuple[str, str]: a tuple of *preceding* and *succeeding* whitespaces

        """
        code = node.get_code()

        # preceding whitespaces
        prefix = ''
        for char in code:
            if char not in ' \t\n\r\f\v':
                break
            prefix += char

        # succeeding whitespaces
        suffix = ''
        for char in reversed(code):
            if char not in ' \t\n\r\f\v':
                break
            suffix += char

        return prefix, suffix


class LambdaContext(Context):
    """Lambda (suite) conversion context.

    This class is mainly used for converting **lambda statements**.

    Args:
        node (parso.python.tree.Lambda): parso AST
        config (Config): conversion configurations

    Keyword Args:
        column (int): current indentation level
        keyword (Literal['nonlocal']): keyword for wrapper function
        context (Optional[List[str]]): global context (:term:`namespace`)
        raw (False): raw processing flag

    Note:
        * ``keyword`` should always be ``'nonlocal'``.
        * ``raw`` should always be :data:`False`.

    """

    def _concat(self):
        """Concatenate final string.

        Since conversion of *lambda* statements doesn't involve inserting
        points, this method first simply adds wrapper codes to the buffer
        (:data:`self._buffer <Context._buffer>`); then it adds a *return*
        statement yielding the converted *lambda* suite stored in
        :data:`self._prefix <Context._prefix>` and :data:`self._suffix <Context._suffix>`.

        The wrapper codes include variable declaration rendered from
        :data:`NAME_TEMPLATE`, wrapper function definitions rendered from
        :data:`FUNC_TEMPLATE` and extracted *lambda* statements rendered from
        :data:`LAMBDA_FUNC_TEMPLATE`. If :attr:`self._pep8 <Context._pep8>` is
        :data:`True`, it will insert the codes in compliance with :pep:`8`.

        """
        flag = self.has_walrus(self._root)

        # first, the variables and functions
        indent = self._indentation * self._column
        if self._pep8:
            linesep = self._linesep * (1 if self._column > 0 else 2)
        else:
            linesep = ''
        if self._vars:
            name_list = ' = '.join(sorted(set(self._vars)))
            self._buffer += indent + (
                '%s%s' % (self._linesep, indent)
            ).join(NAME_TEMPLATE) % dict(indentation=self._indentation, name_list=name_list) + self._linesep
        for func in sorted(self._func, key=lambda func: func['name']):
            if self._buffer:
                self._buffer += linesep
            self._buffer += indent + (
                '%s%s' % (self._linesep, indent)
            ).join(FUNC_TEMPLATE) % dict(indentation=self._indentation, **func) + self._linesep
        for lamb in self._lamb:
            if self._buffer:
                self._buffer += linesep
            self._buffer += indent + (
                '%s%s' % (self._linesep, indent)
            ).join(LAMBDA_FUNC_TEMPLATE) % dict(indentation=self._indentation, **lamb) + self._linesep
        if flag and self._pep8:
            blank = 2 if self._column == 0 else 1
            self._buffer += self._linesep * self.missing_whitespaces(prefix=self._buffer, suffix=self._prefix,
                                                                     blank=blank, linesep=self._linesep)

        # then, the `return` statement
        self._buffer += indent + 'return'

        # finally, the source codes
        self._buffer += self._prefix + self._suffix


class ClassContext(Context):
    """Class (suite) conversion context.

    This class is mainly used for converting **class variables**.

    Args:
        node (parso.python.tree.Class): parso AST
        config (Config): conversion configurations

    Keyword Args:
        cls_ctx (str): class context name
        cls_var (Dict[str, str]): mapping for assignment variable and its UUID
        column (int): current indentation level
        keyword (Optional[str]): keyword for wrapper function
        context (Optional[List[str]]): global context (:term:`namespace`)
        raw (False): raw context processing flag
        external (Optional[Dict[str, Literal['global', 'nonlocal']]]):
            mapping of *class variables* declared in :token:`global <global_stmt>` and/or
            :token:`nonlocal <nonlocal_stmt>` statements

    Note:
        ``raw`` should always be :data:`False`.

    """

    @property
    def cls_var(self):
        """Mapping for assignment variable and its UUID (:attr:`self._cls_var <walrus.Context._cls_var>`).

        :rtype: Dict[str, str]

        """
        return self._cls_var

    @property
    def external_variables(self):
        """Assignment expression variable records (:attr:`self._ext_vars <walrus.ClassContext._ext_vars>`).

        The variables are the *left-hand-side* variable name of the assignment expressions
        for *class variables* declared in :token:`global <global_stmt>` and/or
        :token:`nonlocal <nonlocal_stmt>` statements.

        :rtype: Dict[str, Literal['global', 'nonlocal']]

        """
        return self._ext_vars

    @property
    def external_functions(self):
        """Assignment expression wrapper function records (:attr:`self._ext_func <walrus.ClassContext._ext_func>`)
        for *class variables* declared in :token:`global <global_stmt>` and/or :token:`nonlocal <nonlocal_stmt>`
        statements.

        :rtype: List[Function]

        """
        return self._ext_func

    def __init__(self, node, config, *,
                 cls_ctx, cls_var=None,
                 column=0, keyword=None,
                 context=None, raw=False,
                 external=None):
        if cls_var is None:
            cls_var = dict()
        if external is None:
            external = dict()

        #: bool: Raw context processing flag.
        self._cls_raw = raw
        #: Dict[str, str]: Mapping for assignment variable and its UUID.
        self._cls_var = cls_var
        #: str: Class context name.
        self._cls_ctx = cls_ctx

        #: Dict[str, Literal['global', 'nonlocal']]: Original
        #: *left-hand-side* variable names in assignment expressions for
        #: *class variables* declared in :token:`global <global_stmt>` and/or
        #: :token:`nonlocal <nonlocal_stmt>` statements.
        self._ext_vars = external
        #: List[Function]: Converted wrapper functions for *class variables* declared in
        #: :token:`global <global_stmt>` and/or :token:`nonlocal <nonlocal_stmt>` statements
        #: described as :class:`Function`.
        self._ext_func = list()

        super().__init__(node=node, config=config, context=context,
                         column=column, keyword=keyword, raw=raw)

    def _process_suite_node(self, node, func=False, raw=False, cls_ctx=None):
        """Process indented suite (:token:`suite` or others).

        Args:
            node (parso.tree.NodeOrLeaf): suite node
            func (bool): if ``node`` is suite from function definition
            raw (bool): raw processing flag
            cls_ctx (Optional[str]): class name if ``node`` is in class context

        This method first checks if ``node`` contains assignment expression.
        If not, it will not perform any processing, rather just append the
        original source code to context buffer.

        If ``node`` contains assignment expression, then it will initiate another
        :class:`ClassContext` instance to perform the conversion process on such
        ``node``; whilst if ``func`` is provided, then it will initiate a
        :class:`Context` instance instead.

        Note:
            If ``func`` is True, when initiating the :class:`Context` instance,
            ``keyword`` will be set as ``'nonlocal'``, as in the wrapper function
            it will refer the original *left-hand-side* variable from the outer
            function scope rather than global namespace.

        The method will keep *global* statements (:meth:`Context.global_stmt`)
        from the temporary :class:`Context` (or :class:`ClassContext`) instance in the
        current instance.

        And if ``raw`` is set as :data:`True`, the method will keep records of converted wrapper
        functions (:meth:`Context.functions`), converted *lambda* statements (:meth:`Context.lambdef`)
        and *left-hand-side* variable names (:meth:`Context.variables`), class variable
        (:meth:`ClassContext.cls_var`), external variables (:meth:`ClassContext.external_variables`),
        wrapper functions for external variables (:meth:`ClassContext.external_functions`) into current
        instance as well.

        Important:
            ``raw`` should be :data:`True` only if the ``node`` is in the clause of another *context*,
            where the converted wrapper functions should be inserted.

            However, it seems useless in current implementation.

        """
        if not self.has_walrus(node):
            self += node.get_code()
            return

        indent = self._column + 1
        self += self._linesep + self._indentation * indent

        if cls_ctx is None:
            cls_ctx = self._cls_ctx
        cls_var = self._cls_var

        if func:
            keyword = 'nonlocal'

            # process suite
            ctx = Context(node=node, config=self.config,
                          context=self._context, column=indent,
                          keyword=keyword, raw=raw)
        else:
            keyword = self._keyword

            # process suite
            ctx = ClassContext(node=node, config=self.config,
                               cls_ctx=cls_ctx, cls_var=cls_var,
                               context=self._context, column=indent,
                               keyword=keyword, raw=raw, external=self._ext_vars)
        self += ctx.string.lstrip()

        # keep record
        if raw:
            self._lamb.extend(ctx.lambdef)
            self._vars.extend(ctx.variables)
            self._func.extend(ctx.functions)

            self._cls_var.update(ctx.cls_var)
            self._ext_vars.update(ctx.external_variables)
            self._ext_func.extend(ctx.external_functions)
        self._context.extend(ctx.global_stmt)

    def _process_namedexpr_test(self, node):
        """Process assignment expression (:token:`namedexpr_test`).

        Args:
            node (parso.python.tree.PythonNode): assignment expression node

        This method converts the assignment expression into wrapper function
        and extracts related records for inserting converted codes.

        * The *left-hand-side* variable name will be recorded in
          :attr:`self._vars <walrus.Context._vars>`; and its corresponding UUID will
          be recorded in :attr:`self._cls_var <ClassContext._cls_var>`.
        * The *right-hand-side* expression will be converted using another
          :class:`ClassContext` instance and replaced with a wrapper function call
          rendered from :data:`CLS_CALL_TEMPLATE`; information described as
          :class:`Function` will be recorded into :attr:`self._func <walrus.Context._func>`.

        Important:
            :class:`~walrus.ClassContext` will `mangle`_ *left-hand-side* variable name
            through :meth:`self._mangle <walrus.ClassContext._mangle>` when converting.

            .. _mangle: https://docs.python.org/3/reference/expressions.html?highlight=mangling#atom-identifiers

        For special *class variables* declared in :token:`global <global_stmt>` and/or
        :token:`nonlocal <nonlocal_stmt>` statements:

        * The *left-hand-side* variable name will **NOT** be considered as *class variable*,
          thus shall **NOT** be recorded.
        * The expression will be replaced with a wrapper function call rendered from
          :data:`CLS_EXT_CALL_TEMPLATE`; information described as :class:`Function` will be
          recorded into :attr:`self._ext_func <walrus.ClassContext._ext_func>` instead.

        """
        # split assignment expression
        node_name, _, node_expr = node.children
        name = node_name.value
        nuid = uuid_gen.gen()

        # calculate expression string
        ctx = ClassContext(node=node_expr, config=self.config,
                           cls_ctx=self._cls_ctx, cls_var=self._cls_var,
                           context=self._context, column=self._column,
                           keyword=self._keyword, raw=True,
                           external=self._ext_vars)
        expr = ctx.string.strip()

        self._lamb.extend(ctx.lambdef)
        self._vars.extend(ctx.variables)
        self._func.extend(ctx.functions)
        self._context.extend(ctx.global_stmt)

        self._cls_var.update(ctx.cls_var)
        self._ext_vars.update(ctx.external_variables)
        self._ext_func.extend(ctx.external_functions)

        # if declared in global/nonlocal statements
        external = name in self._ext_vars

        # replacing codes
        if external:
            code = CLS_EXT_CALL_TEMPLATE % dict(cls=self._cls_ctx, name=name, uuid=nuid, expr=expr)
        else:
            code = CLS_CALL_TEMPLATE % dict(cls=self._cls_ctx, name=self._mangle(name), expr=expr)
        prefix, suffix = self.extract_whitespaces(node)
        self += prefix + code + suffix

        if external:
            self._ext_func.append(dict(name=name, uuid=nuid, keyword=self._ext_vars[name]))
            return

        if name in self._context:
            keyword = 'global'
        else:
            keyword = self._keyword

        # keep records
        self._vars.append(name)
        self._func.append(dict(name=name, uuid=nuid, keyword=keyword))
        self._cls_var[self._mangle(name)] = nuid

    def _process_defined_name(self, node):
        """Process defined name (:token:`name`).

        Args:
            node (parso.python.tree.Name): defined name node

        This method processes name of defined *class variables*. The original
        variable name will be replaced with a :obj:`dict` assignment statement
        rendered from :data:`LCL_NAME_TEMPLATE`; and will be recorded in
        :attr:`self._vars <walrus.Context._vars>`; its corresponding UUID will
        be recorded in :attr:`self._cls_var <ClassContext._cls_var>`; information
        described as :class:`Function` will be recorded into
        :attr:`self._func <walrus.Context._func>`.

        Note:
            If the *left-hand-side* variable was declared in :token:`global <global_stmt>`
            and/or :token:`nonlocal <nonlocal_stmt>`, then it shall **NOT** be
            considered as *class variable*.

        """
        name = node.value

        # if declared in global/nonlocal statements
        if name in self._ext_vars:
            self += node.get_code()
            return

        name = self._mangle(name)
        nuid = uuid_gen.gen()

        prefix, _ = self.extract_whitespaces(node)
        self += prefix + LCL_NAME_TEMPLATE % dict(cls=self._cls_ctx, name=name)

        self._vars.append(name)
        self._func.append(dict(name=name, uuid=nuid, keyword=self._keyword))
        self._cls_var[self._mangle(name)] = nuid

    def _process_expr_stmt(self, node):
        """Process variable name (:token:`expr_stmt`).

        Args:
            node (parso.python.tree.ExprStmt): expression statement

        This method processes expression statements in the class context.
        It will search for *left-hand-side* variable names of defined
        class variables and call :meth:`~ClassContext._process_defined_name`
        to process such nodes.

        """
        # right hand side expression
        rhs = node.get_rhs()

        for child in node.children:
            if child == rhs:
                self._process(child)
                continue
            if child.type == 'name':
                self._process_defined_name(child)
                continue
            self += child.get_code()

    def _process_name(self, node):
        """Process variable name (:token:`name`).

        Args:
            node (parso.python.tree.Name): variable name

        This method processes the reference of variables in the class context.
        If the variable is a defined *class variable*, then it will be replaced
        with codes rendered from :data:`LCL_CALL_TEMPLATE`.

        """
        name = self._mangle(node.value)

        if name in self._cls_var:
            prefix, _ = self.extract_whitespaces(node)
            self += prefix + LCL_CALL_TEMPLATE % dict(cls=self._cls_ctx, name=name)
            return

        # normal processing
        self += node.get_code()

    def _process_global_stmt(self, node):
        """Process function definition (:token:`global_stmt`).

        Args:
            node (parso.python.tree.GlobalStmt): global statement node

        This method records all variables declared in a *global* statement
        into :attr:`self._context <walrus.Context._context>` and
        :attr:`self._ext_vars <walrus.ClassContext._ext_vars>`.

        """
        children = iter(node.children)

        # <Keyword: global>
        next(children)
        # <Name: ...>
        name = next(children)
        self._context.append(name.value)
        self._ext_vars[name.value] = 'global'

        while True:
            try:
                # <Operator: ,>
                next(children)
            except StopIteration:
                break

            # <Name: ...>
            name = next(children)
            self._context.append(name.value)
            self._ext_vars[name.value] = 'global'

        # process code
        self += node.get_code()

    def _process_nonlocal_stmt(self, node):
        """Process function definition (:token:`nonlocal_stmt`).

        Args:
            node (parso.python.tree.GlobalStmt): nonlocal statement node

        This method records all variables declared in a *nonlocal* statement
        into :attr:`self._ext_vars <walrus.ClassContext._ext_vars>`.

        """
        children = iter(node.children)

        # <Keyword: nonlocal>
        next(children)
        # <Name: ...>
        name = next(children)
        self._ext_vars[name.value] = 'nonlocal'

        while True:
            try:
                # <Operator: ,>
                next(children)
            except StopIteration:
                break

            # <Name: ...>
            name = next(children)
            self._ext_vars[name.value] = 'nonlocal'

        # process code
        self += node.get_code()

    def _concat(self):
        """Concatenate final string.

        This method tries to inserted the recorded wrapper functions and variables
        at the very location where starts to contain assignment expressions, i.e.
        between the converted codes as :attr:`self._prefix <Context._prefix>` and
        :attr:`self._suffix <Context._suffix>`.

        The inserted codes include wrapper namespace class declaration rendered from
        :data:`CLS_NAME_TEMPLATE` and wrapper function definitions rendered from
        :data:`CLS_GET_FUNC_TEMPLATE` and :data:`CLS_SET_FUNC_TEMPLATE`. If
        :attr:`self._pep8 <Context._pep8>` is :data:`True`, it will insert the codes
        in compliance with :pep:`8`.

        Also, for special *class variables* declared in :token:`global <global_stmt>`
        and/or :token:`nonlocal <nonlocal_stmt>` statements, they will be declared again
        with its original keyword in the wrapper class context rendered from
        :data:`CLS_EXT_VARS_GLOBAL_TEMPLATE` and :data:`CLS_EXT_VARS_NONLOCAL_TEMPLATE`.
        When assigning to to such variables, i.e. they are on *left-hand-side* of
        assignment expressions, the expressions will be assigned with a wrapper function
        rendered from :data:`CLS_EXT_FUNC_TEMPLATE`.

        """
        flag = self.has_walrus(self._root)

        # strip suffix comments
        prefix, suffix = self._strip()

        # first, the prefix codes
        self._buffer += self._prefix + prefix

        # then, the class and functions
        indent = self._indentation * self._column
        linesep = self._linesep
        if flag:
            if self._pep8:
                if (self._node_before_walrus is not None
                        and self._node_before_walrus.type in ('funcdef', 'classdef')
                        and self._column == 0):
                    blank = 2
                else:
                    blank = 1
                self._buffer += self._linesep * self.missing_whitespaces(prefix=self._buffer, suffix='',
                                                                         blank=blank, linesep=self._linesep)
            self._buffer += indent + (
                '%s%s' % (self._linesep, indent)
            ).join(CLS_NAME_TEMPLATE) % dict(indentation=self._indentation, cls=self._cls_ctx) + linesep

        global_list = list()
        nonlocal_list = list()
        for name, keyword in self._ext_vars.items():
            if keyword == 'global':
                global_list.append(name)
            if keyword == 'nonlocal':
                nonlocal_list.append(name)
        if global_list:
            if self._buffer:
                self._buffer += linesep
            name_list = ' = '.join(sorted(set(global_list)))
            self._buffer += indent + CLS_EXT_VARS_GLOBAL_TEMPLATE % dict(
                indentation=self._indentation, name_list=name_list
            ) + self._linesep
        if nonlocal_list:
            if not global_list:
                self._buffer += linesep
            name_list = ' = '.join(sorted(set(nonlocal_list)))
            self._buffer += indent + CLS_EXT_VARS_NONLOCAL_TEMPLATE % dict(
                indentation=self._indentation, name_list=name_list
            ) + self._linesep

        if self._buffer:
            self._buffer += linesep
        self._buffer += indent + (
            '%s%s' % (self._linesep, indent)
        ).join(CLS_GET_FUNC_TEMPLATE) % dict(indentation=self._indentation, cls=self._cls_ctx) + linesep

        if self._buffer:
            self._buffer += linesep
        self._buffer += indent + (
            '%s%s' % (self._linesep, indent)
        ).join(CLS_SET_FUNC_TEMPLATE) % dict(indentation=self._indentation, cls=self._cls_ctx) + linesep

        for func in sorted(self._ext_func, key=lambda func: func['name']):
            if self._buffer:
                self._buffer += linesep
            self._buffer += indent + (
                '%s%s' % (self._linesep, indent)
            ).join(CLS_EXT_FUNC_TEMPLATE) % dict(indentation=self._indentation, cls=self._cls_ctx, **func) + linesep

        # finally, the suffix codes
        if flag and self._pep8:
            blank = 2 if self._column == 0 else 1
            self._buffer += self._linesep * self.missing_whitespaces(prefix=self._buffer, suffix=suffix,
                                                                     blank=blank, linesep=self._linesep)
        self._buffer += suffix

    def _mangle(self, name):
        """Mangle variable names.

        The method mangles variable names as described in `Python documentation`_.

        Args:
            name (str): variable name

        Returns:
            str: mangled variable name

        .. _Python documentation: https://docs.python.org/3/reference/expressions.html#atom-identifiers

        """
        if not name.startswith('__'):
            return name

        # class name contains only underscores
        match0 = re.fullmatch(r'_+', self._cls_ctx)
        if match0 is not None:
            return name

        # starts and ends with exactly two underscores
        match1 = re.match(r'^__[a-zA-Z0-9]+', name)
        match2 = re.match(r'.*[a-zA-Z0-9]__$', name)
        if match1 is not None and match2 is not None:
            return name
        return '_%(cls)s%(name)s' % dict(cls=self._cls_ctx.lstrip('_'), name=name)


###############################################################################
# Public Interface

def convert(code, filename=None, *, source_version=None, linesep=None, indentation=None, pep8=None):
    """Convert the given Python source code string.

    Args:
        code (Union[str, bytes]): the source code to be converted
        filename (Optional[str]): an optional source file name to provide a context in case of error

    Keyword Args:
        source_version (Optional[str]): parse the code as this Python version (uses the latest version by default)
        linesep (Optional[str]): line separator of code (``LF``, ``CRLF``, ``CR``) (auto detect by default)
        indentation (Optional[Union[int, str]]): code indentation style, specify an integer for the number of spaces,
            or ``'t'``/``'tab'`` for tabs (auto detect by default)
        pep8 (Optional[bool]): whether to make code insertion :pep:`8` compliant

    :Environment Variables:
     - :envvar:`WALRUS_SOURCE_VERSION` -- same as the ``source_version`` argument and the ``--source-version`` option
        in CLI
     - :envvar:`WALRUS_LINESEP` -- same as the `linesep` `argument` and the ``--linesep`` option in CLI
     - :envvar:`WALRUS_INDENTATION` -- same as the ``indentation`` argument and the ``--indentation`` option in CLI
     - :envvar:`WALRUS_PEP8` -- same as the ``pep8`` argument and the ``--no-pep8`` option in CLI (logical negation)

    Returns:
        str: converted source code

    """
    # TODO: define UUID generator in the Context class, avoid using a global variable
    # Initialise new UUID4Generator for identifier UUIDs
    global uuid_gen
    uuid_gen = UUID4Generator(dash=False)

    # parse source string
    source_version = _get_source_version_option(source_version)
    module = parso_parse(code, filename=filename, version=source_version)

    # get linesep, indentation and pep8 options
    linesep = _get_linesep_option(linesep)
    indentation = _get_indentation_option(indentation)
    if linesep is None:
        linesep = detect_linesep(code)
    if indentation is None:
        indentation = detect_indentation(code)
    pep8 = _get_pep8_option(pep8)

    # pack conversion configuration
    config = Config(linesep=linesep, indentation=indentation, pep8=pep8)

    # convert source string
    result = Context(module, config).string

    # return conversion result
    return result


def walrus(filename, *, source_version=None, linesep=None, indentation=None, pep8=None, quiet=None, dry_run=False):
    """Convert the given Python source code file. The file will be overwritten.

    Args:
        filename (str): the file to convert

    Keyword Args:
        source_version (Optional[str]): parse the code as this Python version (uses the latest version by default)
        linesep (Optional[str]): line separator of code (``LF``, ``CRLF``, ``CR``) (auto detect by default)
        indentation (Optional[Union[int, str]]): code indentation style, specify an integer for the number of spaces,
            or ``'t'``/``'tab'`` for tabs (auto detect by default)
        pep8 (Optional[bool]): whether to make code insertion :pep:`8` compliant
        quiet (Optional[bool]): whether to run in quiet mode
        dry_run (bool): if :data:`True`, only print the name of the file to convert but do not perform any conversion

    :Environment Variables:
     - :envvar:`WALRUS_SOURCE_VERSION` -- same as the ``source-version`` argument and the ``--source-version`` option
        in CLI
     - :envvar:`WALRUS_LINESEP` -- same as the ``linesep`` argument and the ``--linesep`` option in CLI
     - :envvar:`WALRUS_INDENTATION` -- same as the ``indentation`` argument and the ``--indentation`` option in CLI
     - :envvar:`WALRUS_PEP8` -- same as the ``pep8`` argument and the ``--no-pep8`` option in CLI (logical negation)
     - :envvar:`WALRUS_QUIET` -- same as the ``quiet`` argument and the ``--quiet`` option in CLI

    """
    quiet = _get_quiet_option(quiet)
    if not quiet:
        with TaskLock():
            print('Now converting: %r' % filename, file=sys.stderr)
    if dry_run:
        return

    # read file content
    with open(filename, 'rb') as file:
        content = file.read()

    # detect source code encoding
    encoding = detect_encoding(content)

    # get linesep and indentation
    linesep = _get_linesep_option(linesep)
    indentation = _get_indentation_option(indentation)
    if linesep is None or indentation is None:
        with open(filename, 'r', encoding=encoding) as file:
            if linesep is None:
                linesep = detect_linesep(file)
            if indentation is None:
                indentation = detect_indentation(file)

    # do the dirty things
    result = convert(content, filename=filename, source_version=source_version,
                     linesep=linesep, indentation=indentation, pep8=pep8)

    # overwrite the file with conversion result
    with open(filename, 'w', encoding=encoding, newline='') as file:
        file.write(result)


###############################################################################
# CLI & Entry Point

# option values display
# these values are only intended for argparse help messages
# this shows default values by default, environment variables may override them
__cwd__ = os.getcwd()
__walrus_quiet__ = 'quiet mode' if _get_quiet_option() else 'non-quiet mode'
__walrus_concurrency__ = _get_concurrency_option() or 'auto detect'
__walrus_do_archive__ = 'will do archive' if _get_do_archive_option() else 'will not do archive'
__walrus_archive_path__ = os.path.join(__cwd__, _get_archive_path_option())
__walrus_source_version__ = _get_source_version_option()
__walrus_linesep__ = {
    '\n': 'LF',
    '\r\n': 'CRLF',
    '\r': 'CR',
    None: 'auto detect'
}[_get_linesep_option()]
__walrus_indentation__ = _get_indentation_option()
if __walrus_indentation__ is None:
    __walrus_indentation__ = 'auto detect'
elif __walrus_indentation__ == '\t':
    __walrus_indentation__ = 'tab'
else:
    __walrus_indentation__ = '%d spaces' % len(__walrus_indentation__)
__walrus_pep8__ = 'will conform to PEP 8' if _get_pep8_option() else 'will not conform to PEP 8'


def get_parser():
    """Generate CLI parser.

    Returns:
        argparse.ArgumentParser: CLI parser for walrus

    """
    parser = argparse.ArgumentParser(prog='walrus',
                                     usage='walrus [options] <Python source files and directories...>',
                                     description='Back-port compiler for Python 3.8 assignment expressions.')
    parser.add_argument('-V', '--version', action='version', version=__version__)
    parser.add_argument('-q', '--quiet', action='store_true', default=None,
                        help='run in quiet mode (current: %s)' % __walrus_quiet__)
    parser.add_argument('-C', '--concurrency', action='store', type=int, metavar='N',
                        help='the number of concurrent processes for conversion (current: %s)' % __walrus_concurrency__)
    parser.add_argument('--dry-run', action='store_true',
                        help='list the files to be converted without actually performing conversion and archiving')

    archive_group = parser.add_argument_group(title='archive options',
                                              description="backup original files in case there're any issues")
    archive_group.add_argument('-na', '--no-archive', action='store_false', dest='do_archive', default=None,
                               help='do not archive original files (current: %s)' % __walrus_do_archive__)
    archive_group.add_argument('-k', '--archive-path', action='store', default=__walrus_archive_path__, metavar='PATH',
                               help='path to archive original files (current: %(default)s)')
    archive_group.add_argument('-r', '--recover', action='store', dest='recover_file', metavar='ARCHIVE_FILE',
                               help='recover files from a given archive file')
    archive_group.add_argument('-r2', action='store_true', help='remove the archive file after recovery')
    archive_group.add_argument('-r3', action='store_true', help='remove the archive file after recovery, '
                                                                'and remove the archive directory if it becomes empty')

    convert_group = parser.add_argument_group(title='convert options', description='conversion configuration')
    convert_group.add_argument('-vs', '-vf', '--source-version', '--from-version', action='store', metavar='VERSION',
                               default=__walrus_source_version__, choices=WALRUS_SOURCE_VERSIONS,
                               help='parse source code as this Python version (current: %(default)s)')
    convert_group.add_argument('-l', '--linesep', action='store',
                               help='line separator (LF, CRLF, CR) to read '
                                    'source files (current: %s)' % __walrus_linesep__)
    convert_group.add_argument('-t', '--indentation', action='store', metavar='INDENT',
                               help='code indentation style, specify an integer for the number of spaces, '
                                    "or 't'/'tab' for tabs (current: %s)" % __walrus_indentation__)
    convert_group.add_argument('-n8', '--no-pep8', action='store_false', dest='pep8', default=None,
                               help='do not make code insertion PEP 8 compliant (current: %s)' % __walrus_pep8__)

    parser.add_argument('files', action='store', nargs='*', metavar='<Python source files and directories...>',
                        help='Python source files and directories to be converted')

    return parser


def do_walrus(filename, **kwargs):
    """Wrapper function to catch exceptions."""
    try:
        walrus(filename, **kwargs)
    except Exception:  # pylint: disable=broad-except
        with TaskLock():
            print('Failed to convert file: %r' % filename, file=sys.stderr)
            traceback.print_exc()


def main(argv=None):
    """Entry point for walrus.

    Args:
        argv (Optional[List[str]]): CLI arguments

    :Environment Variables:
     - :envvar:`WALRUS_QUIET` -- same as the ``--quiet`` option in CLI
     - :envvar:`WALRUS_CONCURRENCY` -- same as the ``--concurrency`` option in CLI
     - :envvar:`WALRUS_DO_ARCHIVE` -- same as the ``--no-archive`` option in CLI (logical negation)
     - :envvar:`WALRUS_ARCHIVE_PATH` -- same as the ``--archive-path`` option in CLI
     - :envvar:`WALRUS_SOURCE_VERSION` -- same as the ``--source-version`` option in CLI
     - :envvar:`WALRUS_LINESEP` -- same as the ``--linesep`` option in CLI
     - :envvar:`WALRUS_INDENTATION` -- same as the ``--indentation`` option in CLI
     - :envvar:`WALRUS_PEP8` -- same as the ``--no-pep8`` option in CLI (logical negation)

    """
    parser = get_parser()
    args = parser.parse_args(argv)

    # get options
    quiet = _get_quiet_option(args.quiet)
    processes = _get_concurrency_option(args.concurrency)
    do_archive = _get_do_archive_option(args.do_archive)
    archive_path = _get_archive_path_option(args.archive_path)

    # check if doing recovery
    if args.recover_file:
        recover_files(args.recover_file)
        if not args.quiet:
            print('Recovered files from archive: %r' % args.recover_file, file=sys.stderr)
        # TODO: maybe implement deletion in bpc-utils?
        if args.r2 or args.r3:
            os.remove(args.recover_file)
            if args.r3:
                archive_dir = os.path.dirname(os.path.realpath(args.recover_file))
                if not os.listdir(archive_dir):
                    os.rmdir(archive_dir)
        return

    # fetch file list
    if not args.files:
        parser.error('no Python source files or directories are given')
    filelist = sorted(detect_files(args.files))

    # terminate if no valid Python source files detected
    if not filelist:
        if not args.quiet:
            print('Warning: no valid Python source files found in %r' % args.files, file=sys.stderr)
        return

    # make archive
    if do_archive and not args.dry_run:
        archive_files(filelist, archive_path)

    # process files
    options = {
        'source_version': args.source_version,
        'linesep': args.linesep,
        'indentation': args.indentation,
        'pep8': args.pep8,
        'quiet': quiet,
        'dry_run': args.dry_run,
    }
    map_tasks(do_walrus, filelist, kwargs=options, processes=processes)


if __name__ == '__main__':
    sys.exit(main())
