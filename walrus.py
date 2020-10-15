# -*- coding: utf-8 -*-
"""Back-port compiler for Python 3.8 assignment expressions."""

import argparse
import os
import pathlib
import re
import sys
import traceback

import f2format
import parso
import tbtrim
from bpc_utils import (BaseContext, BPCSyntaxError, Config, TaskLock, archive_files,
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
CLS_TEMPLATE = "(__import__('builtins').locals().__setitem__(%(name)r, %(expr)s), %(name)s)[1]"


class Context(BaseContext):
    """General conversion context.

    Args:
        node (parso.tree.NodeOrLeaf): parso AST
        config (Config): conversion configurations

    Keyword Args:
        indent_level (int): current indentation level
        keyword (Optional[Literal['global', 'nonlocal']]): keyword for wrapper function
        context (Optional[List[str]]): global context (:term:`namespace`)
        raw (bool): raw processing flag

    Important:
        ``raw`` should be :data:`True` only if the ``node`` is in the clause of another *context*,
        where the converted wrapper functions should be inserted.

        Typically, only if ``node`` is an assignment expression (:token:`namedexpr_test`) node,
        ``raw`` will be set as :data:`True`, in consideration of nesting assignment expressions.

    For the :class:`Context` class of :mod:`walrus` module,
    it will process nodes with following methods:

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

      - :meth:`ClassContext._process_defined_name`

    * :token:`nonlocal_stmt`

      - :meth:`ClassContext._process_nonlocal_stmt`

    * :token:`stringliteral`

      * :meth:`ClassContext._process_strings`
      * :meth:`ClassContext._process_string_context`

    * :token:`f_string`

      * :meth:`ClassContext._process_fstring`
      * :meth:`ClassContext._process_string_context`

    """

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

    def __init__(self, node, config, *, indent_level=0, keyword=None, context=None, raw=False):
        if keyword is None:
            keyword = self.guess_keyword(node)
        if context is None:
            context = list()

        #: Literal['global', 'nonlocal']:
        #: The :token:`global <global_stmt>` / :token:`nonlocal <nonlocal_stmt>` keyword.
        self._keyword = keyword
        #: List[str]: Variable names in :token:`global <global_stmt>` statements.
        self._context = list(context)

        #: List[str]: Original *left-hand-side* variable names in assignment expressions.
        self._vars = list()
        #: List[Lambda]: Converted *lambda* statements described as :class:`Lambda`.
        self._lamb = list()
        #: List[Function]: Converted wrapper functions described as :class:`Function`.
        self._func = list()

        # call super init
        super().__init__(node, config, indent_level=indent_level, raw=raw)

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

        """
        if not self.has_expr(node):
            self += node.get_code()
            return

        indent = self._indent_level + 1
        self += self._linesep + self._indentation * indent

        if func:
            keyword = 'nonlocal'
        else:
            keyword = self._keyword

        # process suite
        if cls_ctx is None:
            ctx = Context(node=node, config=self.config,
                          context=self._context, indent_level=indent,
                          keyword=keyword, raw=raw)
        else:
            ctx = ClassContext(cls_ctx=cls_ctx,
                               node=node, config=self.config,
                               context=self._context, indent_level=indent,
                               keyword=keyword, raw=raw)
        self += ctx.string.lstrip()

        # keep records
        if raw:
            self._lamb.extend(ctx.lambdef)
            self._vars.extend(ctx.variables)
            self._func.extend(ctx.functions)
        self._context.extend(ctx.global_stmt)

    def _process_string_context(self, node):
        """Process string contexts (:token:`stringliteral`).

        Args:
            node (parso.python.tree.PythonNode): string literals node

        This method first checks if ``node`` contains assignment expression.
        If not, it will not perform any processing, rather just append the
        original source code to context buffer. Later it will check if
        ``node`` contains *debug f-string*. If not, it will process the
        *regular* processing on each child of such ``node``.

        See Also:
            The method calls :meth:`f2format.Context.has_debug_fstring`
            to detect *debug f-strings*.

        Otherwise, it will initiate a new :class:`StringContext` instance
        to perform the conversion process on such ``node``, which will first
        use :mod:`f2format` to convert those formatted string literals.

        Important:
            When initialisation, ``raw`` parameter **must** be set to :data:`True`;
            as the converted wrapper functions should be inserted in the *outer*
            context, rather than the new :class:`StringContext` instance.

        After conversion, the method will keep records of converted wrapper
        functions (:meth:`Context.functions`), converted *lambda* statements (:meth:`Context.lambdef`)
        and *left-hand-side* variable names (:meth:`Context.variables`) into current instance as well.

        """
        if not self.has_expr(node):
            self += node.get_code()
            return

        # TODO: reconstruct f2format and implement such method for the case
        # if not f2format.Context.has_debug_fstring(node):
        if True:  # pylint: disable=using-constant-test
            for child in node.children:
                self._process(child)
            return

        # initiate new context
        ctx = StringContext(node=node, config=self.config, context=self._context,
                            indent_level=self._indent_level, keyword=self._keyword, raw=True)
        self += ctx.string.lstrip()

        # keep record
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
        nuid = self._uuid_gen.gen()

        # calculate expression string
        ctx = Context(node=node_expr, config=self.config,
                      context=self._context, indent_level=self._indent_level,
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

        This method converts the whole class suite context with
        :meth:`~Context._process_suite_node` through
        :class:`ClassContext` respectively.

        """
        # <Name: ...>
        name = node.name

        # <Keyword: class>
        # <Name: ...>
        # [<Operator: (>, PythonNode(arglist, [...]]), <Operator: )>]
        # <Operator: :>
        for child in node.children[:-1]:
            self._process(child)

        # PythonNode(suite, [...]) / PythonNode(simple_stmt, [...])
        suite = node.children[-1]
        self._process_suite_node(suite, cls_ctx=name.value)

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
        if not self.has_expr(node):
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
        indent = self._indent_level + 1
        ctx = LambdaContext(node=next(children), config=self.config,
                            context=self._context, indent_level=indent,
                            keyword='nonlocal')
        suite = ctx.string.strip()

        # keep record
        nuid = self._uuid_gen.gen()
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
        flag = any((self._vars, self._func, self._lamb))  # if have codes to insert

        # strip suffix comments
        prefix, suffix = self.split_comments(self._suffix, self._linesep)
        suffix_linesep = re.match(rf'^(?P<linesep>({self._linesep})*)', suffix, flags=re.ASCII).group('linesep')

        # first, the prefix codes
        self._buffer += self._prefix + prefix + suffix_linesep
        if flag and self._pep8 and self._buffer:
            if (self._node_before_expr is not None
                    and self._node_before_expr.type in ('funcdef', 'classdef')
                    and self._indent_level == 0):
                blank = 2
            else:
                blank = 1
            self._buffer += self._linesep * self.missing_newlines(prefix=self._buffer, suffix='',
                                                                  expected=blank, linesep=self._linesep)

        # then, the variables and functions
        indent = self._indentation * self._indent_level
        if self._pep8:
            linesep = self._linesep * (1 if self._indent_level > 0 else 2)
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
            blank = 2 if self._indent_level == 0 else 1
            self._buffer += self._linesep * self.missing_newlines(prefix=self._buffer, suffix=suffix,
                                                                  expected=blank, linesep=self._linesep)
        self._buffer += suffix.lstrip(self._linesep)

    @classmethod
    def has_expr(cls, node):
        """Check if node has assignment expression (:token:`namedexpr_test`).

        Args:
            node (parso.tree.NodeOrLeaf): parso AST

        Returns:
            bool: if ``node`` has assignment expression

        """
        if cls.is_walrus(node):
            return True
        if hasattr(node, 'children'):
            for child in node.children:
                if cls.has_expr(child):
                    return True
        return False

    # backward compatibility and auxiliary alias
    has_walrus = has_expr

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


class StringContext(Context):
    """String (f-string) conversion context.

    This class is mainly used for converting **formatted strings**.

    Args:
        node (parso.python.tree.Lambda): parso AST
        config (Config): conversion configurations

    Keyword Args:
        indent_level (int): current indentation level
        keyword (Literal['nonlocal']): keyword for wrapper function
        context (Optional[List[str]]): global context (:term:`namespace`)
        raw (Literal[True]): raw processing flag

    Note:
        * ``raw`` should always be :data:`True`.

    As the conversion in :class:`Context` changes the original expression,
    which may change the content of *debug f-string*.

    """

    def __init__(self, node, config, *, indent_level=0, keyword=None, context=None, raw=False):
        # convert using f2format first
        prefix, suffix = self.extract_whitespaces(node)
        code = f2format.convert(node.get_code().strip())
        node = parso_parse(code, filename=config.filename, version=config.source_version)

        # call super init
        super().__init__(node, config, indent_level=indent_level,
                         keyword=keyword, context=context, raw=raw)
        self._buffer = prefix + self._buffer + suffix


class LambdaContext(Context):
    """Lambda (suite) conversion context.

    This class is mainly used for converting **lambda statements**.

    Args:
        node (parso.python.tree.Lambda): parso AST
        config (Config): conversion configurations

    Keyword Args:
        indent_level (int): current indentation level
        keyword (Literal['nonlocal']): keyword for wrapper function
        context (Optional[List[str]]): global context (:term:`namespace`)
        raw (Literal[False]): raw processing flag

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
        flag = self.has_expr(self._root)

        # first, the variables and functions
        indent = self._indentation * self._indent_level
        if self._pep8:
            linesep = self._linesep * (1 if self._indent_level > 0 else 2)
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
            blank = 2 if self._indent_level == 0 else 1
            self._buffer += self._linesep * self.missing_newlines(prefix=self._buffer, suffix=self._prefix,
                                                                  expected=blank, linesep=self._linesep)

        # then, the `return` statement
        self._buffer += indent + 'return'

        # finally, the source codes
        self._buffer += self._prefix + self._suffix


class ClassContext(Context):
    """Class (suite) conversion context.

    This class is mainly used for converting *:term:`class variable <class-variable>`*.

    Args:
        node (parso.python.tree.Class): parso AST
        config (Config): conversion configurations

    Keyword Args:
        cls_ctx (str): class context name
        cls_var (Dict[str, str]): mapping for assignment variable and its UUID
        indent_level (int): current indentation level
        keyword (Optional[str]): keyword for wrapper function
        context (Optional[List[str]]): global context (:term:`namespace`)
        raw (Literal[False]): raw context processing flag
        external (Optional[Dict[str, Literal['global', 'nonlocal']]]):
            mapping of :term:`class variable <class-variable>` declared in :token:`global <global_stmt>` and/or
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
        for :term:`class variable <class-variable>` declared in :token:`global <global_stmt>` and/or
        :token:`nonlocal <nonlocal_stmt>` statements.

        :rtype: Dict[str, Literal['global', 'nonlocal']]

        """
        return self._ext_vars

    @property
    def external_functions(self):
        """Assignment expression wrapper function records (:attr:`self._ext_func <walrus.ClassContext._ext_func>`)
        for :term:`class variable <class-variable>` declared in :token:`global <global_stmt>` and/or
        :token:`nonlocal <nonlocal_stmt>` statements.

        :rtype: List[Function]

        """
        return self._ext_func

    def __init__(self, node, config, *, cls_ctx, cls_var=None, indent_level=0,
                 keyword=None, context=None, raw=False, external=None):
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
        #: :term:`class variable <class-variable>` declared in
        #: :token:`global <global_stmt>` and/or :token:`nonlocal <nonlocal_stmt>`
        #: statements.
        self._ext_vars = external
        #: List[Function]: Converted wrapper functions for :term:`class variable <class-variable>`
        #: declared in :token:`global <global_stmt>` and/or :token:`nonlocal <nonlocal_stmt>`
        #: statements described as :class:`Function`.
        self._ext_func = list()

        super().__init__(node=node, config=config, context=context,
                         indent_level=indent_level, keyword=keyword, raw=raw)

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

        """
        if not self.has_expr(node):
            self += node.get_code()
            return

        indent = self._indent_level + 1
        self += self._linesep + self._indentation * indent

        if cls_ctx is None:
            cls_ctx = self._cls_ctx
        cls_var = self._cls_var

        if func:
            keyword = 'nonlocal'

            # process suite
            ctx = Context(node=node, config=self.config,
                          context=self._context, indent_level=indent,
                          keyword=keyword, raw=raw)
        else:
            keyword = self._keyword

            # process suite
            ctx = ClassContext(node=node, config=self.config,
                               cls_ctx=cls_ctx, cls_var=cls_var,
                               context=self._context, indent_level=indent,
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

    def _process_string_context(self, node):
        """Process string contexts (:token:`stringliteral`).

        Args:
            node (parso.python.tree.PythonNode): string literals node

        This method first checks if ``node`` contains assignment expression.
        If not, it will not perform any processing, rather just append the
        original source code to context buffer.

        If ``node`` contains assignment expression, then it will initiate a new
        :class:`ClassStringContext` instance to perform the conversion process
        on such ``node``, which will first use :mod:`f2format` to convert those
        formatted string literals.

        Important:
            When initialisation, ``raw`` parameter **must** be set to :data:`True`;
            as the converted wrapper functions should be inserted in the *outer*
            context, rather than the new :class:`ClassStringContext` instance.

        After conversion, the method will keep records of converted wrapper
        functions (:attr:`Context.functions`), converted *lambda* statements (:attr:`Context.lambdef`)
        and *left-hand-side* variable names (:attr:`Context.variables`), class variable
        (:attr:`ClassContext.cls_var`), external variables (:attr:`ClassContext.external_variables`),
        wrapper functions for external variables (:attr:`ClassContext.external_functions`) into current
        instance as well.

        """
        if not self.has_expr(node):
            self += node.get_code()
            return

        # initiate new context
        ctx = ClassStringContext(node=node, config=self.config,
                                 cls_ctx=self._cls_ctx, cls_var=self._cls_var,
                                 context=self._context, indent_level=self._indent_level,
                                 keyword=self._keyword, raw=True, external=self._ext_vars)
        self += ctx.string.lstrip()

        # keep record
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
          :class:`ClassContext` instance and replaced with a wrapper tuple with
          attribute setting from :data:`CLS_TEMPLATE`; information described as
          :class:`Function` will be recorded into :attr:`self._func <walrus.Context._func>`.

        Important:
            :class:`~walrus.ClassContext` will `mangle`_ *left-hand-side* variable name
            through :meth:`self._mangle <walrus.ClassContext._mangle>` when converting.

            .. _mangle: https://docs.python.org/3/reference/expressions.html?highlight=mangling#atom-identifiers

        For special :term:`class variable <class-variable>` declared in :token:`global <global_stmt>`
        and/or :token:`nonlocal <nonlocal_stmt>` statements:

        * The *left-hand-side* variable name will **NOT** be considered as *class variable*,
          thus shall **NOT** be recorded.
        * The expression will be replaced with a wrapper function call rendered from
          :data:`CALL_TEMPLATE`; information described as :class:`Function` will be
          recorded into :attr:`self._ext_func <walrus.ClassContext._ext_func>` instead.

        """
        # split assignment expression
        node_name, _, node_expr = node.children
        name = node_name.value
        nuid = self._uuid_gen.gen()

        # calculate expression string
        ctx = ClassContext(node=node_expr, config=self.config,
                           cls_ctx=self._cls_ctx, cls_var=self._cls_var,
                           context=self._context, indent_level=self._indent_level,
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
            code = CALL_TEMPLATE % dict(name=name, uuid=nuid, expr=expr)
        else:
            code = CLS_TEMPLATE % dict(name=self._mangle(name), expr=expr)
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

        This method processes name of defined :term:`class variable <class-variable>`. The original
        variable name will be recorded in :attr:`self._vars <walrus.Context._vars>`;
        its corresponding UUID will be recorded in :attr:`self._cls_var <ClassContext._cls_var>`;
        information described as :class:`Function` will be recorded into
        :attr:`self._func <walrus.Context._func>`.

        Note:
            If the *left-hand-side* variable was declared in :token:`global <global_stmt>`
            and/or :token:`nonlocal <nonlocal_stmt>`, then it shall **NOT** be
            considered as *class variable*.

        """
        name = node.value
        self += node.get_code()

        # if declared in global/nonlocal statements
        if name in self._ext_vars:
            return

        name = self._mangle(name)
        nuid = self._uuid_gen.gen()

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

    def _process_strings(self, node):
        """Process concatenable strings (:token:`stringliteral`).

        Args:
            node (parso.python.tree.PythonNode): concatentable strings node

        As in Python, adjacent string literals can be concatenated in certain
        cases, as described in the `documentation`_. Such concatenable strings
        may contain formatted string literals (:term:`f-string`) within its scope.

        _documentation: https://docs.python.org/3/reference/lexical_analysis.html#string-literal-concatenation

        """
        self._process_string_context(node)

    def _process_fstring(self, node):
        """Process formatted strings (:token:`f_string`).

        Args:
            node (parso.python.tree.PythonNode): formatted strings node

        """
        self._process_string_context(node)

    def _concat(self):
        """Concatenate final string.

        This method tries to inserted the recorded wrapper functions and variables
        at the very location where starts to contain assignment expressions, i.e.
        between the converted codes as :attr:`self._prefix <Context._prefix>` and
        :attr:`self._suffix <Context._suffix>`.

        For special :term:`class variable <class-variable>` declared in :token:`global <global_stmt>`
        and/or :token:`nonlocal <nonlocal_stmt>` statements, when assigning to
        to such variables, i.e. they are on *left-hand-side* of assignment
        expressions, the expressions will be assigned with a wrapper function
        rendered from :data:`FUNC_TEMPLATE`.

        """
        flag = self.has_expr(self._root)

        # strip suffix comments
        prefix, suffix = self.split_comments(self._suffix, self._linesep)
        suffix_linesep = re.match(rf'^(?P<linesep>({self._linesep})*)', suffix, flags=re.ASCII).group('linesep')

        # first, the prefix codes
        self._buffer += self._prefix + prefix + suffix_linesep

        # then, the class and functions
        indent = self._indentation * self._indent_level
        linesep = self._linesep
        if flag and self._pep8:
            if (self._node_before_expr is not None
                    and self._node_before_expr.type in ('funcdef', 'classdef')
                    and self._indent_level == 0):
                blank = 2
            else:
                blank = 1
            self._buffer += self._linesep * self.missing_newlines(prefix=self._buffer, suffix='',
                                                                  expected=blank, linesep=self._linesep)

        for index, func in enumerate(sorted(self._ext_func, key=lambda func: func['name'])):
            if index > 0:
                self._buffer += linesep
            self._buffer += indent + (
                '%s%s' % (self._linesep, indent)
            ).join(FUNC_TEMPLATE) % dict(indentation=self._indentation, cls=self._cls_ctx, **func) + linesep

        # finally, the suffix codes
        if flag and self._pep8:
            blank = 2 if self._indent_level == 0 else 1
            self._buffer += self._linesep * self.missing_newlines(prefix=self._buffer, suffix=suffix,
                                                                  expected=blank, linesep=self._linesep)
        self._buffer += suffix.lstrip(self._linesep)

    def _mangle(self, name):
        """Mangle variable names.

        The method mangles variable names as described in `Python documentation`_.

        Args:
            name (str): variable name

        Returns:
            str: mangled variable name

        .. _Python documentation: https://docs.python.org/3/reference/expressions.html#atom-identifiers

        """
        # should only perform mangling if variable name begins with two or more underscores
        # and does not end in two or more underscores
        if not name.startswith('__') or name.endswith('__'):
            return name

        # perform mangling, remove leading underscores from the class name when inserting
        return '_%(cls)s%(name)s' % dict(cls=self._cls_ctx.lstrip('_'), name=name)


class ClassStringContext(ClassContext):
    """String (f-string) conversion context.

    This class is mainly used for converting **formatted strings**
    inside a class suite (:term:`ClassVar <class-variable>`).

    Args:
        node (parso.python.tree.Class): parso AST
        config (Config): conversion configurations

    Keyword Args:
        cls_ctx (str): class context name
        cls_var (Dict[str, str]): mapping for assignment variable and its UUID
        indent_level (int): current indentation level
        keyword (Optional[str]): keyword for wrapper function
        context (Optional[List[str]]): global context (:term:`namespace`)
        raw (Literal[True]): raw context processing flag
        external (Optional[Dict[str, Literal['global', 'nonlocal']]]):
            mapping of :term:`class variable <class-variable>` declared in :token:`global <global_stmt>` and/or
            :token:`nonlocal <nonlocal_stmt>` statements

    Note:
        ``raw`` should always be :data:`True`.

    As the conversion in :class:`ClassContext` introduced quotes (``'``)
    into the converted codes, it may cause conflicts on the string parsing
    if the assignment expression was inside a formatted string.

    Therefore, we will use :mod:`f2format` ahead to convert such formatted
    strings into normat :func:`str.format` calls then convert any assignment
    expressions it may contain.

    """

    def __init__(self, node, config, *, cls_ctx, cls_var=None, indent_level=0,
                 keyword=None, context=None, raw=False, external=None):
        # convert using f2format first
        prefix, suffix = self.extract_whitespaces(node)
        code = f2format.convert(node.get_code().strip())
        node = parso_parse(code, filename=config.filename, version=config.source_version)

        # call super init
        super().__init__(node=node, config=config, cls_ctx=cls_ctx, cls_var=cls_var,
                         context=context, indent_level=indent_level, keyword=keyword,
                         raw=raw, external=external)
        self._buffer = prefix + self._buffer + suffix


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
    config = Config(linesep=linesep, indentation=indentation, pep8=pep8,
                    filename=filename, source_version=source_version)

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
    parser.add_argument('-s', '--simple', action='store', nargs='?', dest='simple_args', const='', metavar='FILE',
                        help='this option tells the program to operate in "simple mode"; '
                             'if a file name is provided, the program will convert the file but print conversion '
                             'result to standard output instead of overwriting the file; '
                             'if no file names are provided, read code for conversion from standard input and print '
                             'conversion result to standard output; '
                             'in "simple mode", no file names shall be provided via positional arguments')

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

    options = {
        'source_version': args.source_version,
        'linesep': args.linesep,
        'indentation': args.indentation,
        'pep8': args.pep8,
    }

    # check if running in simple mode
    if args.simple_args is not None:
        if args.files:
            parser.error('no Python source files or directories shall be given as positional arguments in simple mode')
        if not args.simple_args:  # read from stdin
            code = sys.stdin.read()
        else:  # read from file
            filename = args.simple_args
            options['filename'] = filename
            with open(filename, 'rb') as file:
                code = file.read()
        sys.stdout.write(convert(code, **options))  # print conversion result to stdout
        return

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
    options.update({
        'quiet': quiet,
        'dry_run': args.dry_run,
    })
    map_tasks(do_walrus, filelist, kwargs=options, processes=processes)


if __name__ == '__main__':
    sys.exit(main())
