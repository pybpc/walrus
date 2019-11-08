# -*- coding: utf-8 -*-

import argparse
import glob
import locale
import os
import re
import shutil
import sys
import uuid

import parso
import tbtrim

__all__ = ['walrus', 'convert']

# multiprocessing may not be supported
try:        # try first
    import multiprocessing
except ImportError:  # pragma: no cover
    multiprocessing = None
else:       # CPU number if multiprocessing supported
    if os.name == 'posix' and 'SC_NPROCESSORS_CONF' in os.sysconf_names:  # pragma: no cover
        CPU_CNT = os.sysconf('SC_NPROCESSORS_CONF')
    elif hasattr(os, 'sched_getaffinity'):  # pragma: no cover
        CPU_CNT = len(os.sched_getaffinity(0))  # pylint: disable=E1101
    else:  # pragma: no cover
        CPU_CNT = os.cpu_count() or 1
finally:    # alias and aftermath
    mp = multiprocessing
    del multiprocessing

# version string
__version__ = '0.1.0.dev0'

# from configparser
BOOLEAN_STATES = {'1': True, '0': False,
                  'yes': True, 'no': False,
                  'true': True, 'false': False,
                  'on': True, 'off': False}

# environs
LOCALE_ENCODING = locale.getpreferredencoding(False)

# macros
grammar_regex = re.compile(r"grammar(\d)(\d)\.txt")
WALRUS_VERSION = sorted(filter(lambda version: version >= '3.8',  # when Python starts to have walrus operator
                               map(lambda path: '%s.%s' % grammar_regex.match(os.path.split(path)[1]).groups(),
                                   glob.glob(os.path.join(parso.__path__[0], 'python', 'grammar??.txt')))))
del grammar_regex


class ConvertError(SyntaxError):
    """Parso syntax error."""


class ContextError(RuntimeError):
    """Missing conversion context."""


###############################################################################
# Traceback trim (tbtrim)

# root path
ROOT = os.path.dirname(os.path.realpath(__file__))


def predicate(filename):  # pragma: no cover
    if os.path.basename(filename) == 'walrus':
        return True
    return ROOT in os.path.realpath(filename)


tbtrim.set_trim_rule(predicate, strict=True, target=(ConvertError, ContextError))

###############################################################################
# Main convertion implementation

# walrus wrapper template
FUNC_TEMPLATE = '''
def __walrus_wrapper_%(name)s_%(uuid)s():
    """Wrapper function for assignment expression `%(expr)s`."""
    %(keyword)s %(name)s
    %(name)s = %(expr)s
    return %(name)s
'''.splitlines()


def parse(string, source, error_recovery=False):
    """Parse source string.

    Args:
     - `string` -- `str`, context to be converted
     - `source` -- `str`, source of the context
     - `error_recovery` -- `bool`, see `parso.Grammar.parse`

    Envs:
     - `WALRUS_VERSION` -- convert against Python version (same as `--python` option in CLI)

    Returns:
     - `parso.python.tree.Module` -- parso AST

    Raises:
     - `ConvertError` -- when `parso.ParserSyntaxError` raised

    """
    try:
        return parso.parse(string, error_recovery=error_recovery,
                           version=os.getenv('WALRUS_VERSION', WALRUS_VERSION[-1]))
    except parso.ParserSyntaxError as error:
        message = '%s: <%s: %r> from %s' % (error.message, error.error_leaf.token_type,
                                            error.error_leaf.value, source)
        raise ConvertError(message).with_traceback(error.__traceback__) from None


class ConvertContext:
    """Conversion context."""

    @property
    def tabsize(self):
        """Indentation tab size.

        Returns:
         - `int` -- inndentation tab size

        """
        return self._indent

    @property
    def linesep(self):
        """Line separator.

        Returns:
         - `str` -- line separator

        """
        return self._linesep

    @property
    def column(self):
        """Current indentation.

        Returns:
         - `int` -- current inndentation

        """
        return self._column

    def __init__(self, node, indent=0, tabsize=None):
        """"Hold process context.

        Args:
         - `node` -- `Union[parso.python.tree.PythonNode, parso.python.tree.PythonLeaf]`, parso AST
         - `indent` -- `int`, tab size addon for suites
         - `tabsize` -- `int`, indentation tab size

        Envs:
         - `WALRUS_LINESEP` -- line separator to process source files (same as `--linesep` option in CLI)

        """
        self._linesep = os.getenv('WALRUS_LINESEP', os.linesep)
        self._column = node.get_first_leaf().column + indent
        self._indent = tabsize or indent
        self._func = list()
        self._vars = list()

    def extract(self, node):
        """Process assignment expression (`namedexpr_test`).

        Args:
        - `node` -- `parso.python.tree.PythonNode`, assignment expression node

        Returns:
         - `str` -- converted string

        """
        # split assignment expression
        node_name, _, node_expr = node.children
        name = node_name.value
        expr = walk(node_expr, self)
        uid = uuid.uuid4().hex

        function = self.make_func(name, expr, uid)
        string = '__walrus_wrapper_%s_%s()' % (name, uid)

        if name not in self._vars:
            variable = '%s%s = locals().get(%r)%s' % ('\t'.expandtabs(self.column),
                                                      name, name, self.linesep)
            self._vars.append(variable)
        self._func.append(function)

        return string

    def make_func(self, name, expr, uid):
        """Generate wrapper function.

        Args:
         - `name` -- `str`, variable name
         - `expr` -- `str`, variable expression
         - `uid` -- `str`, hash ID of wrapped node

        Returns:
         - `str` -- wrapper function

        """
        return (
            '%s%s' % (self.linesep, '\t'.expandtabs(self.column))
        ).join(FUNC_TEMPLATE) % dict(keyword='nonlocal' if self.column else 'global',
                                     name=name, expr=expr.strip(), uuid=uid) + self.linesep

    def finalize(self, prefix, suffix):
        """Format final results.

        Args:
         - `prefix` -- `str`, prefix string
         - `suffix` -- `str`, suffix string

        Returns:
         - `str` -- finalised converted string

        """
        variables = self.linesep.join(self._vars)
        functions = self.linesep.join(self._func)

        return prefix + variables + functions + suffix


def process_suite(node, indent, *, async_ctx=None):
    """Process node with suite.

    Args:
     - `node` -- `parso.python.tree.PythonNode`, parso AST
     - `indent` -- `int`, indentation tab size

    Kwds:
     - `async_ctx` -- `parso.python.tree.Keyword`, `async` keyword AST node

    Returns:
     - `str` -- processed source string

    """
    if async_ctx is None:
        prefix = ''
        ctx = ConvertContext(node, indent)
    else:
        prefix = async_ctx.get_code()
        ctx = ConvertContext(async_ctx, indent)
    suffix = ''

    children = iter(node.children)
    for child in children:
        prefix += walk(child, ctx)
        if child.type == 'operator' and child.value == ':':
            prefix += ctx.linesep
            break

    for child in children:
        bufpre, bufsuf = check_suffix(walk(child, ctx))
        prefix += bufpre
        suffix += bufsuf

    return ctx.finalize(prefix, suffix)


def has_walrus(node):
    """Check if node has assignment expression.

    Args:
     - `node` -- `Union[parso.python.tree.PythonNode, parso.python.tree.PythonLeaf]`, node to search

    Return:
     - `bool` -- if node has assignment expression

    """
    if node.type == 'test_namedexpr':
        return True
    if not hasattr(node, 'children'):
        return False
    return any(map(has_walrus, node.children))


def find_walrus(node, root=0):
    """Find node to insert walrus context.

    Args:
     - `node` -- `parso.python.tree.Module`, parso AST
     - `root` -- `int`, index for insertion (based on `node`)

    Returns:
     - `int` -- index for insertion (based on `node`)

    """
    for index, child in enumerate(node.children, start=1):
        if has_walrus(child):
            return root
        if child.get_first_leaf().column == 0:
            root = index
    return -1


def check_indent(node):
    """Check indentation tab size.

    Args:
     - `node` -- `parso.python.tree.Module`, parso AST

    Returns:
     - `int` -- indentation tab size

    """
    for child in node.children:
        if child.type != 'suite':
            if hasattr(child, 'children'):
                tabsize = check_indent(child)
                if tabsize > 0:
                    return tabsize
            continue
        return child.children[1].get_first_leaf().column
    return 0


def check_suffix(string):
    """Strip comments from string.

    Args:
     - `string` -- `str`, buffer string

    Returns:
     - `str` -- prefix comments
     - `str` -- suffix strings

    """
    prefix = ''
    suffix = ''

    lines = iter(string.splitlines(True))
    for line in lines:
        if line.strip().startswith('#'):
            prefix += line
            continue
        suffix += line
        break

    for line in lines:
        suffix += line
    return prefix, suffix


def process_module(node):
    """Walk top nodes of the AST module.

    Args:
     - `node` -- `parso.python.tree.Module`, parso AST

    Envs:
     - `WALRUS_LINESEP` -- line separator to process source files (same as `--linesep` option in CLI)

    Returns:
     - `str` -- processed source string

    """
    WALRUS_TABSIZE = int(os.getenv('WALRUS_TABSIZE', __walrus_tabsize__))

    prefix = ''
    suffix = ''

    tab = check_indent(node) or WALRUS_TABSIZE
    ctx = ConvertContext(node, tabsize=tab)
    pos = find_walrus(node)

    for index, child in enumerate(node.children):
        if index < pos:
            prefix += walk(child, ctx)
        else:
            bufpre, bufsuf = check_suffix(walk(child, ctx))
            prefix += bufpre
            suffix += bufsuf
    return ctx.finalize(prefix, suffix)


def walk(node, ctx=None):
    """Walk parso AST.

    Args:
     - `node` -- `Union[parso.python.tree.Module, parso.python.tree.PythonNode, parso.python.tree.PythonLeaf]`,
                 parso AST
     - `ctx` -- `ConvertContext`, conversion context

    Envs:
     - `WALRUS_LINESEP` -- line separator to process source files (same as `--linesep` option in CLI)

    Returns:
     - `str` -- converted string

    """
    if isinstance(node, parso.python.tree.Module):
        return process_module(node)
    if ctx is None:
        raise ContextError('missing conversion context for node %r' % node)

    # string buffer
    string = ''

    if node.type == 'try_stmt':
        pass

    # if node.type in ('funcdef', 'classdef', 'if_stmt', 'while_stmt', 'for_stmt', 'with_stmt'):
    if node.type in ('funcdef', 'classdef'):
        return process_suite(node, ctx.tabsize)

    if node.type == 'async_stmt':
        child_1st = node.children[0]
        child_2nd = node.children[1]

        flag_1st = child_1st.type == 'keyword' and child_1st.value == 'async'
        flag_2nd = child_2nd.type in ('funcdef', 'with_stmt', 'for_stmt')

        if flag_1st and flag_2nd:  # pragma: no cover
            return process_suite(child_2nd, ctx.tabsize, async_ctx=child_1st)

    if isinstance(node, parso.python.tree.PythonLeaf):
        string += node.get_code()

    if hasattr(node, 'children'):
        for child in node.children:
            if child.type == 'namedexpr_test':
                string += ctx.extract(child)
            else:
                string += walk(child, ctx)

    return string


def convert(string, source='<unknown>'):
    """The main conversion process.

    Args:
     - `string` -- `str`, context to be converted
     - `source` -- `str`, source of the context

    Envs:
     - `WALRUS_VERSION` -- convert against Python version (same as `--python` option in CLI)
     - `WALRUS_LINESEP` -- line separator to process source files (same as `--linesep` option in CLI)

    Returns:
     - `str` -- converted string

    """
    # parse source string
    module = parse(string, source)

    # convert source string
    string = walk(module)

    # return converted string
    return string


def walrus(filename):
    """Wrapper works for conversion.

    Args:
     - `filename` -- `str`, file to be converted

    Envs:
     - `WALRUS_QUIET` -- run in quiet mode (same as `--quiet` option in CLI)
     - `WALRUS_ENCODING` -- encoding to open source files (same as `--encoding` option in CLI)
     - `WALRUS_VERSION` -- convert against Python version (same as `--python` option in CLI)
     - `WALRUS_LINESEP` -- line separator to process source files (same as `--linesep` option in CLI)

    """
    WALRUS_QUIET = BOOLEAN_STATES.get(os.getenv('WALRUS_QUIET', '0').casefold(), False)
    if not WALRUS_QUIET:  # pragma: no cover
        print('Now converting %r...' % filename)

    # fetch encoding
    encoding = os.getenv('WALRUS_ENCODING', LOCALE_ENCODING)

    # file content
    with open(filename, 'r', encoding=encoding) as file:
        text = file.read()

    # do the dirty things
    text = convert(text, filename)

    # dump back to the file
    with open(filename, 'w', encoding=encoding) as file:
        file.write(text)


###############################################################################
# CLI & entry point

# default values
__cwd__ = os.getcwd()
__archive__ = os.path.join(__cwd__, 'archive')
__walrus_version__ = os.getenv('WALRUS_VERSION', WALRUS_VERSION[-1])
__walrus_encoding__ = os.getenv('WALRUS_ENCODING', LOCALE_ENCODING)
__walrus_linesep__ = os.getenv('WALRUS_LINESEP', os.linesep)
__walrus_tabsize__ = os.getenv('WALRUS_TABSIZE', '4')


def get_parser():
    """Generate CLI parser.

    Returns:
     - `argparse.ArgumentParser` -- CLI parser for walrus

    """
    parser = argparse.ArgumentParser(prog='walrus',
                                     usage='walrus [options] <python source files and folders...>',
                                     description='Back-port compiler for Python 3.8 positional-only parameters.')
    parser.add_argument('-V', '--version', action='version', version=__version__)
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='run in quiet mode')

    archive_group = parser.add_argument_group(title='archive options',
                                              description="duplicate original files in case there's any issue")
    archive_group.add_argument('-na', '--no-archive', action='store_false', dest='archive',
                               help='do not archive original files')
    archive_group.add_argument('-p', '--archive-path', action='store', default=__archive__, metavar='PATH',
                               help='path to archive original files (%s)' % __archive__)

    convert_group = parser.add_argument_group(title='convert options',
                                              description='compatibility configuration for none-unicode files')
    convert_group.add_argument('-c', '--encoding', action='store', default=__walrus_encoding__, metavar='CODING',
                               help='encoding to open source files (%s)' % __walrus_encoding__)
    convert_group.add_argument('-v', '--python', action='store', metavar='VERSION',
                               default=__walrus_version__, choices=WALRUS_VERSION,
                               help='convert against Python version (%s)' % __walrus_version__)
    convert_group.add_argument('-s', '--linesep', action='store', default=__walrus_linesep__, metavar='SEP',
                               help='line separator to process source files (%r)' % __walrus_linesep__)
    convert_group.add_argument('-nl', '--no-linting', action='store_false', dest='linting',
                               help='do not lint converted codes')
    convert_group.add_argument('-t', '--tabsize', action='store', default=__walrus_tabsize__, metavar='INDENT',
                               help='indentation tab size (%s)' % __walrus_tabsize__, type=int)

    parser.add_argument('file', nargs='+', metavar='SOURCE', default=__cwd__,
                        help='python source files and folders to be converted (%s)' % __cwd__)

    return parser


def find(root):  # pragma: no cover
    """Recursively find all files under root.

    Args:
     - `root` -- `os.PathLike`, root path to search

    Returns:
     - `Generator[str, None, None]` -- yield all files under the root path

    """
    file_list = list()
    for entry in os.scandir(root):
        if entry.is_dir():
            file_list.extend(find(entry.path))
        elif entry.is_file():
            file_list.append(entry.path)
        elif entry.is_symlink():  # exclude symbolic links
            continue
    yield from file_list


def rename(path, root):
    """Rename file for archiving.

    Args:
     - `path` -- `os.PathLike`, file to rename
     - `root` -- `os.PathLike`, archive path

    Returns:
     - `str` -- the archiving path

    """
    stem, ext = os.path.splitext(path)
    name = '%s-%s%s' % (stem, uuid.uuid4(), ext)
    return os.path.join(root, name)


def main(argv=None):
    """Entry point for walrus.

    Args:
     - `argv` -- `List[str]`, CLI arguments (default: None)

    Envs:
     - `WALRUS_QUIET` -- run in quiet mode (same as `--quiet` option in CLI)
     - `WALRUS_ENCODING` -- encoding to open source files (same as `--encoding` option in CLI)
     - `WALRUS_VERSION` -- convert against Python version (same as `--python` option in CLI)
     - `WALRUS_LINESEP` -- line separator to process source files (same as `--linesep` option in CLI)
     - `WALRUS_LINTING` -- lint converted codes (same as `--linting` option in CLI)
     - `WALRUS_TABSIZE` -- indentation tab size (same as `--tabsize` option in CLI)

    """
    parser = get_parser()
    args = parser.parse_args(argv)

    # set up variables
    ARCHIVE = args.archive_path
    os.environ['WALRUS_VERSION'] = args.python
    os.environ['WALRUS_ENCODING'] = args.encoding
    os.environ['WALRUS_LINESEP'] = args.linesep
    os.environ['WALRUS_TABSIZE'] = str(args.tabsize)
    WALRUS_QUIET = os.getenv('WALRUS_QUIET')
    os.environ['WALRUS_QUIET'] = '1' if args.quiet else ('0' if WALRUS_QUIET is None else WALRUS_QUIET)
    WALRUS_LINTING = os.getenv('WALRUS_LINTING')
    os.environ['WALRUS_LINTING'] = '1' if args.linting else ('0' if WALRUS_LINTING is None else WALRUS_LINTING)

    # make archive directory
    if args.archive:  # pragma: no cover
        os.makedirs(ARCHIVE, exist_ok=True)

    # fetch file list
    filelist = list()
    for path in args.file:
        if os.path.isfile(path):
            if args.archive:  # pragma: no cover
                dest = rename(path, root=ARCHIVE)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy(path, dest)
            filelist.append(path)
        if os.path.isdir(path):  # pragma: no cover
            if args.archive:
                shutil.copytree(path, rename(path, root=ARCHIVE))
            filelist.extend(find(path))

    # check if file is Python source code
    ispy = lambda file: (os.path.isfile(file) and (os.path.splitext(file)[1] in ('.py', '.pyw')))
    filelist = sorted(filter(ispy, filelist))

    # if no file supplied
    if not filelist:  # pragma: no cover
        parser.error('argument PATH: no valid source file found')

    # process files
    if mp is None or CPU_CNT <= 1:
        [walrus(filename) for filename in filelist]  # pylint: disable=expression-not-assigned # pragma: no cover
    else:
        with mp.Pool(processes=CPU_CNT) as pool:
            pool.map(walrus, filelist)


if __name__ == '__main__':
    sys.exit(main())
