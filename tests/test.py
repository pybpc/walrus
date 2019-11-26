# -*- coding: utf-8 -*-
"""Unittest cases."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from walrus import convert, get_parser
from walrus import main as main_func
from walrus import walrus as core_func

# root path
ROOT = os.path.dirname(os.path.realpath(__file__))

# environs
os.environ['WALRUS_QUIET'] = 'true'
os.environ['WALRUS_ENCODING'] = 'utf-8'
os.environ['WALRUS_LINESEP'] = 'LF'


def read_text_file(filename, encoding='utf-8'):
    """Read text file."""
    with open(filename, 'r', encoding=encoding) as file:
        return file.read()


def write_text_file(filename, content, encoding='utf-8'):
    """Write text file."""
    with open(filename, 'w', encoding=encoding) as file:
        file.write(content)


class TestWalrus(unittest.TestCase):
    """Test case."""
    all_test_cases = [fn[:-3] for fn in os.listdir(os.path.join(ROOT, 'sample')) if fn.endswith('.py')]

    def test_get_parser(self):
        """Test the argument parser."""
        parser = get_parser()
        args = parser.parse_args(['-na', '-q', '-p/tmp/',
                                  '-cgb2312', '-v3.8',
                                  'test1.py', 'test2.py'])

        self.assertIs(args.quiet, True,
                      'run in quiet mode')
        self.assertIs(args.archive, False,
                      'do not archive original files')
        self.assertEqual(args.archive_path, '/tmp/',
                         'path to archive original files')
        self.assertEqual(args.encoding, 'gb2312',
                         'encoding to open source files')
        self.assertEqual(args.python, '3.8',
                         'convert against Python version')
        self.assertEqual(args.file, ['test1.py', 'test2.py'],
                         'python source files and folders to be converted')

    def test_main(self):
        """Test the main entrypoint."""
        with tempfile.TemporaryDirectory(prefix='walrus-test-') as tmpdir:
            for test_case in TestWalrus.all_test_cases:
                shutil.copy(os.path.join(ROOT, 'sample', test_case + '.py'), tmpdir)

            main_func([tmpdir])

            for test_case in TestWalrus.all_test_cases:
                with self.subTest(test_case=test_case):
                    original_output = read_text_file(os.path.join(ROOT, 'sample', test_case + '.out'))
                    converted_output = subprocess.check_output([sys.executable, os.path.join(tmpdir, test_case + '.py')], universal_newlines=True)  # pylint: disable=line-too-long
                    self.assertEqual(original_output, converted_output)

    def test_core(self):
        """Test the core function."""
        with tempfile.TemporaryDirectory(prefix='walrus-test-') as tmpdir:
            for test_case in TestWalrus.all_test_cases:
                shutil.copy(os.path.join(ROOT, 'sample', test_case + '.py'), tmpdir)

            for entry in os.scandir(tmpdir):
                core_func(entry.path)

            for test_case in TestWalrus.all_test_cases:
                with self.subTest(test_case=test_case):
                    original_output = read_text_file(os.path.join(ROOT, 'sample', test_case + '.out'))
                    converted_output = subprocess.check_output([sys.executable, os.path.join(tmpdir, test_case + '.py')], universal_newlines=True)  # pylint: disable=line-too-long
                    self.assertEqual(original_output, converted_output)

    def test_convert(self):
        """Test the convert function."""
        with tempfile.TemporaryDirectory(prefix='walrus-test-') as tmpdir:
            for test_case in TestWalrus.all_test_cases:
                with self.subTest(test_case=test_case):
                    original_code = read_text_file(os.path.join(ROOT, 'sample', test_case + '.py'))
                    original_output = read_text_file(os.path.join(ROOT, 'sample', test_case + '.out'))
                    converted_code = convert(original_code)
                    converted_filename = os.path.join(tmpdir, test_case + '.py')
                    write_text_file(converted_filename, converted_code)
                    converted_output = subprocess.check_output([sys.executable, converted_filename], universal_newlines=True)  # pylint: disable=line-too-long
                    self.assertEqual(original_output, converted_output)


if __name__ == '__main__':
    sys.exit(unittest.main())
