# -*- coding: utf-8 -*-

import argparse
import glob
import locale
import os
import re
import shutil
import sys
import uuid
import warnings

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
__version__ = '0.2.0'

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
    pass


class ConvertWarning(Warning):
    pass


###############################################################################
# Traceback trim (tbtrim)

# root path
ROOT = os.path.dirname(os.path.realpath(__file__))


def predicate(filename):  # pragma: no cover
    if os.path.basename(filename) == 'walrus':
        return True
    return ROOT in os.path.realpath(filename)


tbtrim.set_trim_rule(predicate, strict=True, target=ConvertError)

###############################################################################
# Main convertion implementation


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


def process_comp(node):
    """Process comparison node.

    Args:
     - `node` -- `parso.python.tree.PythonNode`, parso AST for comparison node

    Returns:
     - `str` -- converted comparison string
     - `Union[str, None]` -- walrus assignment string

    """
    string = ''
    assign = None

    for child in node.children:
        if hasattr(child, 'children'):
            pass

    return string, assign


def process_if(node):
    """Process `if` statement.

    Args:
     - `node` -- `parso.python.tree.IfStmt`, parso AST for `if` statement

    Envs:
     - `WALRUS_LINSEP` -- line separator to process source files (same as `--linesep` option in CLI)

    Returns:
     - `str` -- converted string

    """
    WALRUS_LINESEP = os.getenv('WALRUS_LINESEP', os.linesep)

    # string buffer
    string = ''

    for child in node.children:
        if isinstance(child, parso.python.tree.PythonLeaf):
            string += child.get_code()
        else:
            report = process_comp(child)
            if report[1] is not None:  # walrus assignment string
                string = '%s%s%s%s' % (report[1],
                                       WALRUS_LINESEP,
                                       '\t'.expandtabs(node.get_first_leaf().column),
                                       string)
            string += report[0]  #  converted comparison string

    return string


def walk(node):
    """Walk parso AST.

    Args:
     - `node` -- `Union[parso.python.tree.Module, parso.python.tree.PythonNode, parso.python.tree.PythonLeaf]`,
                 parso AST

    Envs:
     - `WALRUS_LINSEP` -- line separator to process source files (same as `--linesep` option in CLI)

    Returns:
     - `str` -- converted string

    """
    # string buffer
    string = ''

    if node.type == 'if_stmt':
        return process_if(node)

    if isinstance(node, parso.python.tree.PythonLeaf):
        string += node.get_code()

    if hasattr(node, 'children'):
        for child in node.children:
            if child.type == 'namedexpr_test':
                warnings.warn('unsupported assignment expression convertion in %s' % node.type, ConvertWarning)
            string += walk(child)

    return string


def convert(string, source='<unknown>'):
    """The main conversion process.

    Args:
     - `string` -- `str`, context to be converted
     - `source` -- `str`, source of the context

    Envs:
     - `WALRUS_VERSION` -- convert against Python version (same as `--python` option in CLI)
     - `WALRUS_LINSEP` -- line separator to process source files (same as `--linesep` option in CLI)

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
     - `WALRUS_LINSEP` -- line separator to process source files (same as `--linesep` option in CLI)

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
     - `WALRUS_LINSEP` -- line separator to process source files (same as `--linesep` option in CLI)

    """
    parser = get_parser()
    args = parser.parse_args(argv)

    # set up variables
    ARCHIVE = args.archive_path
    os.environ['WALRUS_VERSION'] = args.python
    os.environ['WALRUS_ENCODING'] = args.encoding
    os.environ['WALRUS_LINSEP'] = args.linesep
    WALRUS_QUIET = os.getenv('WALRUS_QUIET')
    os.environ['WALRUS_QUIET'] = '1' if args.quiet else ('0' if WALRUS_QUIET is None else WALRUS_QUIET)

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
        mp.Pool(processes=CPU_CNT).map(walrus, filelist)


if __name__ == '__main__':
    sys.exit(main())
