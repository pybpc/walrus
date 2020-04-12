# -*- coding: utf-8 -*-
"""Back-port compiler for Python 3.8 assignment expressions."""

import argparse
import functools
import io
import os
import sys

import parso
import tbtrim
from bpc_utils import (CPU_CNT, BPCSyntaxError, Config, UUID4Generator, archive_files,
                       detect_encoding, detect_files, detect_indentation, detect_linesep,
                       get_parso_grammar_versions, mp, parse_boolean_state, parse_indentation,
                       parse_linesep, parso_parse)

__all__ = ['main', 'walrus', 'convert']

# version string
__version__ = '0.1.4'

###############################################################################
# Auxiliaries

# get supported source versions
WALRUS_VERSIONS = get_parso_grammar_versions(minimum='3.8')

# will be set in every call to `convert()`
uuid_gen = None  # TODO: will be refactored into the Context class

# option default values
_default_quiet = False
_default_do_archive = True
_default_archive_path = 'archive'
_default_source_version = WALRUS_VERSIONS[-1]
_default_linesep = None  # auto detect
_default_indentation = None  # auto detect
_default_pep8 = True

# option getter utility functions
# option value precedence is: explicit value (CLI/API arguments) > environment variable > default value


def _get_quiet_option(explicit=None):
    """Get the value for the ``quiet`` option.

    Args:
        explicit (Optional[bool]): the value explicitly specified by user,
            ``None`` if not specified

    Returns:
        bool: the value for the ``quiet`` option

    :Environment Variables:
     - :envvar:`WALRUS_QUIET` -- the value in environment variable

    """
    if explicit is not None:
        return explicit
    env_value = parse_boolean_state(os.getenv('WALRUS_QUIET'))
    if env_value is not None:
        return env_value
    return _default_quiet


def _get_do_archive_option(explicit=None):
    """Get the value for the ``do_archive`` option.

    Args:
        explicit (Optional[bool]): the value explicitly specified by user,
            ``None`` if not specified

    Returns:
        bool: the value for the ``do_archive`` option

    :Environment Variables:
     - :envvar:`WALRUS_DO_ARCHIVE` -- the value in environment variable

    """
    if explicit is not None:
        return explicit
    env_value = parse_boolean_state(os.getenv('WALRUS_DO_ARCHIVE'))
    if env_value is not None:
        return env_value
    return _default_do_archive


def _get_archive_path_option(explicit=None):
    """Get the value for the ``archive_path`` option.

    Args:
        explicit (Optional[str]): the value explicitly specified by user,
            ``None`` if not specified

    Returns:
        str: the value for the ``archive_path`` option

    :Environment Variables:
     - :envvar:`WALRUS_ARCHIVE_PATH` -- the value in environment variable

    """
    if explicit:
        return explicit
    env_value = os.getenv('WALRUS_ARCHIVE_PATH')
    if env_value:
        return env_value
    return _default_archive_path


def _get_source_version_option(explicit=None):
    """Get the value for the ``source_version`` option.

    Args:
        explicit (Optional[str]): the value explicitly specified by user,
            ``None`` if not specified

    Returns:
        str: the value for the ``source_version`` option

    :Environment Variables:
     - :envvar:`WALRUS_SOURCE_VERSION` -- the value in environment variable

    """
    if explicit:
        return explicit
    env_value = os.getenv('WALRUS_SOURCE_VERSION')
    if env_value:
        return env_value
    return _default_source_version


def _get_linesep_option(explicit=None):
    r"""Get the value for the ``linesep`` option.

    Args:
        explicit (Optional[str]): the value explicitly specified by user,
            ``None`` if not specified

    Returns:
        Optional[Literal['\\n', '\\r\\n', '\\r']]: the value for the ``linesep`` option;
        ``None`` means *auto detection* at runtime

    :Environment Variables:
     - :envvar:`WALRUS_LINESEP` -- the value in environment variable

    """
    if explicit:
        return explicit
    env_value = parse_linesep(os.getenv('WALRUS_LINESEP'))
    if env_value:
        return env_value
    return _default_linesep


def _get_indentation_option(explicit=None):
    """Get the value for the ``indentation`` option.

    Args:
        explicit (Optional[str]): the value explicitly specified by user,
            ``None`` if not specified

    Returns:
        Optional[str]: the value for the ``indentation`` option;
        ``None`` means *auto detection* at runtime

    :Environment Variables:
     - :envvar:`WALRUS_INDENTATION` -- the value in environment variable

    """
    if explicit:
        return explicit
    env_value = parse_indentation(os.getenv('WALRUS_INDENTATION'))
    if env_value:
        return env_value
    return _default_indentation


def _get_pep8_option(explicit=None):
    """Get the value for the ``pep8`` option.

    Args:
        explicit (Optional[str]): the value explicitly specified by user,
            ``None`` if not specified

    Returns:
        bool: the value for the ``pep8`` option

    :Environment Variables:
     - :envvar:`WALRUS_PEP8` -- the value in environment variable

    """
    if explicit is not None:
        return explicit
    env_value = parse_boolean_state(os.getenv('WALRUS_PEP8'))
    if env_value is not None:
        return env_value
    return _default_pep8


###############################################################################
# Traceback trim (tbtrim)

# root path
ROOT = os.path.dirname(os.path.realpath(__file__))


def predicate(filename):  # pragma: no cover
    if os.path.basename(filename) == 'walrus':
        return True
    return ROOT in os.path.realpath(filename)


tbtrim.set_trim_rule(predicate, strict=True, target=BPCSyntaxError)

###############################################################################
# Main convertion implementation

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
## locals dict
LCL_DICT_TEMPLATE = '_walrus_wrapper_%(cls)s_dict = dict()'
LCL_NAME_TEMPLATE = '_walrus_wrapper_%(cls)s_dict[%(name)r]'
LCL_CALL_TEMPLATE = '__WalrusWrapper%(cls)s.get_%(name)s_%(uuid)s()'
LCL_VARS_TEMPLATE = '''\
[setattr(%(cls)s, k, v) for k, v in _walrus_wrapper_%(cls)s_dict.items()]
del _walrus_wrapper_%(cls)s_dict
'''.splitlines()  # `str.splitlines` will remove trailing newline
## class clause
CLS_CALL_TEMPLATE = '__WalrusWrapper%(cls)s.set_%(name)s_%(uuid)s(%(expr)s)'
CLS_NAME_TEMPLATE = '''\
class __WalrusWrapper%(cls)s:
%(indentation)s"""Wrapper class for assignment expression."""
'''.splitlines()  # `str.splitlines` will remove trailing newline
CLS_FUNC_TEMPLATE = '''\
%(indentation)s@staticmethod
%(indentation)sdef set_%(name)s_%(uuid)s(expr):
%(indentation)s%(indentation)s"""Wrapper function for assignment expression."""
%(indentation)s%(indentation)s_walrus_wrapper_%(cls)s_dict[%(name)r] = expr
%(indentation)s%(indentation)sreturn _walrus_wrapper_%(cls)s_dict[%(name)r]

%(indentation)s@staticmethod
%(indentation)sdef get_%(name)s_%(uuid)s():
%(indentation)s%(indentation)s"""Wrapper function for assignment expression."""
%(indentation)s%(indentation)sif %(name)r in _walrus_wrapper_%(cls)s_dict:
%(indentation)s%(indentation)s%(indentation)sreturn _walrus_wrapper_%(cls)s_dict[%(name)r]
%(indentation)s%(indentation)sraise NameError('name %%r is not defined' %% %(name)r)
'''.splitlines()  # `str.splitlines` will remove trailing newline


class Context:
    """Conversion context."""

    @property
    def string(self):
        return self._buffer

    @property
    def lambdef(self):
        return self._lamb

    @property
    def variables(self):
        return self._vars

    @property
    def functions(self):
        return self._func

    @property
    def global_stmt(self):
        if self._root.type == 'funcdef':
            return list()
        return self._context

    def __init__(self, node, config, *,
                 column=0, keyword=None,
                 context=None, raw=False):
        """Conversion context.

        Args:
            node (parso.tree.NodeOrLeaf): parso AST
            config (bpc_utils.Config): convertion configurations

        Keyword Args:
            column (int): current indentation level
            keyword (Optional[Union[Literal['global'], Literal['nonlocal']]]): keyword for wrapper function
            context (Optional[List[str]]): global context
            raw (bool): raw processing flag

        :Environment Variables:
         - :envvar:`WALRUS_LINESEP` -- line separator to process source files (same as ``--linesep`` option in CLI)
         - :envvar:`WALRUS_INDENTATION` -- indentation tab size (same as ``--tabsize`` option in CLI)
         - :envvar:`WALRUS_LINTING` -- lint converted codes (same as ``--linting`` option in CLI)

        """
        if keyword is None:
            keyword = self.guess_keyword(node)
        if context is None:
            context = list()

        self.config = config
        self._indentation = config.indentation  # indentation style
        self._linesep = config.linesep  # line seperator

        # TODO: all options will be stored as attributes, no need to write about env vars in method docstrings
        self._pep8 = config.pep8

        self._root = node  # root node
        self._column = column  # current indentation
        self._keyword = keyword  # global / nonlocal keyword
        self._context = list(context)  # names in global statements

        self._prefix_or_suffix = True  # flag if buffer is now prefix
        self._node_before_walrus = None  # node preceding node with walrus

        self._prefix = ''  # codes before insersion point
        self._suffix = ''  # codes after insersion point
        self._buffer = ''  # final result

        self._vars = list()  # variable initialisation
        self._lamb = list()  # converted lambda definitions ({param, suite, uuid})
        self._func = list()  # wrapper functions ({name, uuid, keyword})

        self._walk(node)  # traverse children
        if raw:
            self._buffer = self._prefix + self._suffix
        else:
            self._concat()  # generate final result

    def __iadd__(self, code):
        """Support of ``+=`` operator.

        If :attr:`self._prefix_or_suffix <walrus.Context._prefix_or_suffix>` is ``True``, then
        the ``code`` will be appended to :attr:`self._prefix <walrus.Context._prefix>`; else
        it will be appended to :attr:`self._suffix <walrus.Context._suffix>`.

        Args:
            code (str): code string

        Returns:
            Context: the object itself

        """
        if self._prefix_or_suffix:
            self._prefix += code
        else:
            self._suffix += code
        return self

    def __str__(self):
        """Returns :attr:`self._buffer <walrus.Context._buffer>`."""
        return self._buffer.strip()

    def _walk(self, node):
        """Start traversing the AST module.

        Args:
            node (parso.tree.NodeOrLeaf): parso AST

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

        """
        # 'funcdef', 'classdef', 'if_stmt', 'while_stmt', 'for_stmt', 'with_stmt', 'try_stmt'
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
        """Process indented suite (`suite` or ...).

        Args:
            node (parso.tree.NodeOrLeaf): suite node
            func (bool): if the suite is of function definition
            raw (bool): raw processing flag
            cls_ctx (Optional[str]): class name when suite if of class contextion

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
        """Process assignment expression (``namedexpr_test``).

        Args:
            node (parso.python.tree.PythonNode): assignment expression node

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
        """Process function definition (``global_stmt``).

        Args:
            node (parso.python.tree.GlobalStmt): global statement node

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
        """Process class definition (``classdef``).

        Args:
            node (parso.python.tree.Class): class node

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
                 + self._linesep

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
                 + ('%s%s' % (self._linesep, indent)).join(LCL_VARS_TEMPLATE) % dict(indentation=self._indentation, cls=name.value) \
                 + self._linesep

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
        """Process function definition (``funcdef``).

        Args:
            node (parso.python.tree.Function): function node

        """
        # 'def' NAME '(' PARAM ')' [ '->' NAME ] ':' SUITE
        for child in node.children[:-1]:
            self._process(child)
        self._process_suite_node(node.children[-1], func=True)

    def _process_lambdef(self, node):
        """Process lambda definition (``lambdef``).

        Args:
            node (parso.python.tree.Lambda): lambda node

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
        """Process if statement (``if_stmt``).

        Args:
            node (parso.python.tree.IfStmt): if node

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

    def _process_while(self, node):
        """Process while statement (``while_stmt``).

        Args:
            node (parso.python.tree.WhileStmt): while node

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
        """Process for statement (``for_stmt``).

        Args:
            node (parso.python.tree.ForStmt): for node

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
        """Process with statement (``with_stmt``).

        Args:
            node (parso.python.tree.WithStmt): with node

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
        """Process try statement (``try_stmt``).

        Args:
            node (parso.python.tree.TryStmt): try node

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
        """Process function argument (``argument``).

        Args:
            node (parso.python.tree.PythonNode): argument node

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
        """Concatenate final string."""
        flag = self.has_walrus(self._root)

        # strip suffix comments
        prefix, suffix = self._strip()

        # first, the prefix codes
        self._buffer += self._prefix + prefix
        if flag and self._pep8 and self._buffer:
            if (self._node_before_walrus is not None \
                    and self._node_before_walrus.type in ('funcdef', 'classdef') \
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
        """Check if node has assignment expression. (``namedexpr_test``)

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
            Union[Literal['global'], Literal['nonlocal']]: keyword

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
        """Check if node is assignment expression.

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
    """Lambda (suite) conversion context."""

    def _concat(self):
        """Concatenate final string."""
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
    """Class (suite) conversion context."""

    @property
    def cls_var(self):
        return self._cls_var

    def __init__(self, node, config, *,
                 cls_ctx, cls_var=None,
                 column=0, keyword=None,
                 context=None, raw=False):
        """Conversion context.

        Args:
            node (parso.tree.NodeOrLeaf): parso AST
            config (bpc_utils.Config): convertion configurations

        Keyword Args:
            cls_ctx (str): class context name
            cls_var (Dict[str, str]): mapping for assignment variable and its UUID
            column (int): current indentation level
            keyword (Optional[str]): keyword for wrapper function
            context (Optional[List[str]]): global context
            raw (bool): raw context processing flag

        :Environment Variables:
         - :envvar:`WALRUS_LINESEP` -- line separator to process source files (same as `--linesep` option in CLI)
         - :envvar:`WALRUS_INDENTATION` -- indentation tab size (same as `--tabsize` option in CLI)
         - :envvar:`WALRUS_LINTING` -- lint converted codes (same as `--linting` option in CLI)

        """
        if cls_var is None:
            cls_var = dict()

        self._cls_raw = raw
        self._cls_var = cls_var
        self._cls_ctx = cls_ctx

        super().__init__(node=node, config=config, context=context,
                         column=column, keyword=keyword, raw=raw)

    def _process_suite_node(self, node, func=False, raw=False, cls_ctx=None):
        """Process indented suite (``suite`` or else).

        Args:
            node (parso.tree.NodeOrLeaf): suite node
            func (bool): if the suite is of function definition
            raw (bool): raw context processing flag
            cls_ctx (Optional[str]): class name when suite if of class contextion

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
                          keyword=keyword)
        else:
            keyword = self._keyword

            # process suite
            ctx = ClassContext(node=node, config=self.config,
                               cls_ctx=cls_ctx, cls_var=cls_var,
                               context=self._context, column=indent,
                               keyword=keyword)
        self += ctx.string.lstrip()

        # keep record
        if raw:
            self._lamb.extend(ctx.lambdef)
            self._vars.extend(ctx.variables)
            self._func.extend(ctx.functions)
            self._cls_var.update(ctx.cls_var)
        self._context.extend(ctx.global_stmt)

    def _process_namedexpr_test(self, node):
        """Process assignment expression (``namedexpr_test``).

        Args:
            node (parso.python.tree.PythonNode): assignment expression node

        """
        # split assignment expression
        node_name, _, node_expr = node.children
        name = node_name.value
        nuid = uuid_gen.gen()

        # calculate expression string
        ctx = ClassContext(node=node_expr, config=self.config,
                           cls_ctx=self._cls_ctx, cls_var=self._cls_var,
                           context=self._context, column=self._column,
                           keyword=self._keyword, raw=True)
        expr = ctx.string.strip()
        self._lamb.extend(ctx.lambdef)
        self._vars.extend(ctx.variables)
        self._func.extend(ctx.functions)
        self._cls_var.update(ctx.cls_var)

        # replacing codes
        code = CLS_CALL_TEMPLATE % dict(cls=self._cls_ctx, name=name, uuid=nuid, expr=expr)
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
        self._cls_var[name] = nuid

    def _process_defined_name(self, node):
        """Process defined name (``name``).

        Args:
            node (parso.python.tree.Name): defined name node

        """
        name = node.value
        nuid = uuid_gen.gen()

        prefix, _ = self.extract_whitespaces(node)
        self += prefix + LCL_NAME_TEMPLATE % dict(cls=self._cls_ctx, name=name)

        self._vars.append(name)
        self._func.append(dict(name=name, uuid=nuid, keyword=self._keyword))
        self._cls_var[name] = nuid

    def _process_expr_stmt(self, node):
        """Process variable name (``expr_stmt``).

        Args:
            node (parso.python.tree.ExprStmt): expression statement

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
        """Process variable name (``name``).

        Args:
            node (parso.python.tree.Name): variable name

        """
        name = node.value

        if name in self._cls_var:
            prefix, _ = self.extract_whitespaces(node)
            self += prefix + LCL_CALL_TEMPLATE % dict(cls=self._cls_ctx, name=name, uuid=self._cls_var[name])
            return

        # normal processing
        self += node.get_code()

    def _concat(self):
        """Concatenate final string."""
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
        for func in sorted(self._func, key=lambda func: func['name']):
            if self._buffer:
                self._buffer += linesep
            self._buffer += indent + (
                '%s%s' % (self._linesep, indent)
            ).join(CLS_FUNC_TEMPLATE) % dict(indentation=self._indentation, cls=self._cls_ctx, **func) + linesep

        # finally, the suffix codes
        if flag and self._pep8:
            blank = 2 if self._column == 0 else 1
            self._buffer += self._linesep * self.missing_whitespaces(prefix=self._buffer, suffix=suffix,
                                                                     blank=blank, linesep=self._linesep)
        self._buffer += suffix


def convert(code, filename=None, *, source_version=None, linesep=None, indentation=None, pep8=None):
    """Convert the given source code string.

    Args:
        code (Union[str, bytes]): the source code to be converted
        filename (Optional[str]): an optional source file name to provide a context in case of error

    Keyword Args:
        source_version (Optional[str]): parse the code as this version (uses the latest version by default)
        linesep (Optional[str]): line separator of code (``LF``, CR``LF, ``CR``) (auto detect by default)
        indentation (Optional[Union[int, str]]): code indentation style, specify an integer for the number of spaces,
            or ``'t'``/``'tab'`` for tabs (auto detect by default)
        pep8 (Optional[bool]): whether to make code insertion :pep:`8` compliant

    :Environment Variables:
     - :envvar:`WALRUS_SOURCE_VERSION` -- same as the ``source_version`` argument and ``--source-version`` option in CLI
     - :envvar:`WALRUS_LINESEP` -- same as the `linesep` `argument` and ``--linesep`` option in CLI
     - :envvar:`WALRUS_INDENTATION` -- same as the ``indentation`` argument and ``--indentation`` option in CLI
     - :envvar:`WALRUS_PEP8` -- same as the ``pep8`` argument and ``--no-pep8`` option in CLI (logical negation)

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

    # convertion configuration
    config = Config(linesep=linesep, indentation=indentation, pep8=pep8)

    # convert source string
    result = Context(module, config).string

    # return converted string
    return result


def walrus(filename, *, source_version=None, linesep=None, indentation=None, pep8=None, quiet=None):
    """Convert the given Python source code file. The file will be overwritten.

    Args:
        filename (Optional[str]): an optional source file name to provide a context in case of error

    Keyword Args:
        source_version (Optional[str]): parse the code as this version (uses the latest version by default)
        linesep (Optional[str]): line separator of code (``LF``, ``CRLF``, ``CR``) (auto detect by default)
        indentation (Optional[Union[int, str]]): code indentation style, specify an integer for the number of spaces,
            or ``'t'``/``'tab'`` for tabs (auto detect by default)
        pep8 (Optional[bool]): whether to make code insertion :pep:`8` compliant
        quiet (Optional[bool]): whether to run in quiet mode

    :Environment Variables:
     - :envvar:`WALRUS_SOURCE_VERSION` -- same as the ``source_version`` argument and ``--source-version`` option in CLI
     - :envvar:`WALRUS_LINESEP` -- same as the ``linesep`` argument and ``--linesep`` option in CLI
     - :envvar:`WALRUS_INDENTATION` -- same as the ``indentation`` argument and ``--indentation`` option in CLI
     - :envvar:`WALRUS_PEP8` -- same as the ``pep8`` argument and ``--no-pep8`` option in CLI (logical negation)
     - :envvar:`WALRUS_QUIET` -- same as the ``quiet`` argument and ``--quiet`` option in CLI

    """
    quiet = _get_quiet_option(quiet)
    if not quiet:  # pragma: no cover
        print('Now converting %r...' % filename)

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
    text = convert(content, filename=filename, source_version=source_version,
                   linesep=linesep, indentation=indentation, pep8=pep8)

    # dump back to the file
    with open(filename, 'w', encoding=encoding, newline='') as file:
        file.write(text)


###############################################################################
# CLI & entry point

# default values
__cwd__ = os.getcwd()
__walrus_archive_path__ = os.path.join(__cwd__, _get_archive_path_option())
__walrus_source_version__ = _get_source_version_option()
__walrus_linesep__ = _get_linesep_option() or 'auto detect'
__walrus_indentation__ = _get_indentation_option() or 'auto detect'


def get_parser():
    """Generate CLI parser.

    Returns:
        argparse.ArgumentParser: CLI parser for walrus

    """
    parser = argparse.ArgumentParser(prog='walrus',
                                     usage='walrus [options] <Python source files and directories...>',
                                     description='Back-port compiler for Python 3.8 assignment expressions.')
    parser.add_argument('-V', '--version', action='version', version=__version__)
    parser.add_argument('-q', '--quiet', action='store_true', help='run in quiet mode')

    archive_group = parser.add_argument_group(title='archive options',
                                              description="backup original files in case there're any issues")
    archive_group.add_argument('-na', '--no-archive', action='store_false', dest='do_archive',
                               help='do not archive original files')
    archive_group.add_argument('-p', '--archive-path', action='store', default=__walrus_archive_path__, metavar='PATH',
                               help='path to archive original files (%(default)s)')

    convert_group = parser.add_argument_group(title='convert options',
                                              description='compatibility configuration for non-unicode files')  # TODO: revise this description
    convert_group.add_argument('-sv', '-fv', '--source-version', '--from-version', action='store', metavar='VERSION',
                               default=__walrus_source_version__, choices=WALRUS_VERSIONS,
                               help='parse source code as Python version (%(default)s)')
    convert_group.add_argument('-s', '--linesep', action='store', default=__walrus_linesep__, metavar='SEP',
                               help='line separator (LF, CRLF, CR) to read source files (%(default)r)')
    convert_group.add_argument('-t', '--indentation', action='store', default=__walrus_indentation__, metavar='INDENT',
                               help='code indentation style, specify an integer for the number of spaces, '
                                    "or 't'/'tab' for tabs (%(default)s)")
    convert_group.add_argument('-n8', '--no-pep8', action='store_false', dest='pep8',
                               help='do not make code insertion PEP 8 compliant')

    parser.add_argument('file', nargs='*', metavar='SOURCE', default=[__cwd__],
                        help='Python source files and directories to be converted (%(default)r)')

    return parser


def main(argv=None):
    """Entry point for walrus.

    Args:
        argv (Optional[List[str]]): CLI arguments

    :Environment Variables:
     - :envvar:`WALRUS_QUIET` -- same as the ``--quiet`` option in CLI
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
    do_archive = _get_do_archive_option(args.do_archive)
    archive_path = _get_archive_path_option(args.archive_path)

    # fetch file list
    filelist = sorted(detect_files(args.file))

    # if no file supplied
    if not filelist:  # pragma: no cover
        parser.error('no valid source file found')

    # make archive
    if do_archive:
        archive_files(filelist, archive_path)

    # process files
    do_walrus = functools.partial(walrus, source_version=args.source_version, linesep=args.linesep,
                                  indentation=args.indentation, pep8=args.pep8, quiet=quiet)
    if mp is None or CPU_CNT <= 1:
        for filename in filelist:  # pragma: no cover
            do_walrus(filename)
    else:
        with mp.Pool(processes=CPU_CNT) as pool:
            pool.map(do_walrus, filelist)


if __name__ == '__main__':
    sys.exit(main())
