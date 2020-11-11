# -*- coding: utf-8 -*-
"""Unittest cases."""

import os
import shutil
import subprocess  # nosec
import sys
import tempfile
import unittest

# root path
ROOT = os.path.dirname(os.path.realpath(__file__))

###############################################################################
# modify import path
# pylint: disable=wrong-import-position
sys.path.insert(0, os.path.abspath(os.path.join(ROOT, '..')))

from walrus import BPCSyntaxError, convert, get_parser  # noqa: E402
from walrus import main as main_func  # noqa: E402
from walrus import walrus as core_func  # noqa: E402

sys.path.pop(0)
###############################################################################


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

    if sys.version_info[:2] < (3, 5):  # pragma: no cover
        # skip unpacking test case on Python < 3.5
        all_test_cases.remove('pep572_exceptional_unpacking')
    if sys.version_info[:2] < (3, 6):  # pragma: no cover
        # skip f-string test case on Python < 3.6
        all_test_cases.remove('pep572_exceptional_fstring')
        all_test_cases.remove('fstring')
        all_test_cases.remove('debug_fstring')
    if sys.version_info[:2] < (3, 7):  # pragma: no cover
        # skip test case for postponed evaluation of annotations on Python < 3.7
        all_test_cases.remove('annotations_pep563')

    def test_get_parser(self):  # TODO: enhance this test
        """Test the argument parser."""
        parser = get_parser()
        args = parser.parse_args(['-na', '-q', '-k/tmp/',
                                  '-vs', '3.8',
                                  'test1.py', 'test2.py'])

        self.assertIs(args.quiet, True)
        self.assertIs(args.do_archive, False)
        self.assertEqual(args.archive_path, '/tmp/')
        self.assertEqual(args.source_version, '3.8')
        self.assertEqual(args.files, ['test1.py', 'test2.py'])

    def test_main(self):
        """Test the main entrypoint."""
        with tempfile.TemporaryDirectory(prefix='walrus-test-') as tmpdir:
            for test_case in TestWalrus.all_test_cases:
                shutil.copy(os.path.join(ROOT, 'sample', test_case + '.py'), tmpdir)

            main_func(['-q', '-na', tmpdir])

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

            for file in os.listdir(tmpdir):
                core_func(os.path.join(tmpdir, file), quiet=True)

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

    def test_invalid(self):
        """Test converting invalid code."""

        pep572_invalid_code = [
            'y := 1',
            'y0 = y1 := 2',
            'dict(x = z := 3)',
            'def foo(answer = p := 42): pass',
            'def bar(answer: q := 24 = 5): pass',
            '(lambda: x := 1)',
            '[i := i+1 for i in range(5)]',
            '[[(j := j) for i in range(5)] for j in range(5)]',
            '[i := 0 for i, j in range(5)]',
            '[i+1 for i in (i := range(5))]',
            '[False and (i := 0) for i, j in range(5)]',
            '[i for i, j in range(5) if True or (j := 1)]',
            '[i+1 for i in (j := range(5))]',
            '[i+1 for i in range(2) for j in (k := range(5))]',
            '[i+1 for i in [j for j in (k := range(5))]]',
            '[i+1 for i in (lambda: (j := range(5)))()]',
            'class Example:\n    [(j := i) for i in range(5)]',
            '(a[i] := x)',
            '(a.b := c)',
            '(a(b) := c)',
            '((a, b) := (1, 2))',
            '([a, b] := [1, 2])',
            '({a, b} := {1, 2})',
            '({a: b} := {1: 2})',
            '(a + b := 1)',
            '(True := 1)',
            '(False := 1)',
            '(None := 1)',
            '(__debug__ := 1)',
            '(... := 1)',
            '(1 := 1)',
            '(await a := x)',
            '(p: int := 1)',
            '(a, b, *c := (1, 2, 3))',
            '(x := 1) = 1',
            '((x := 1) := 1)',
            '(x[0:1] := 1)',
            'totally nonsense',
        ]

        for code in pep572_invalid_code:
            with self.subTest(test_case=code):
                with self.assertRaises(BPCSyntaxError):
                    convert(code)
        # TODO: add more tests


if __name__ == '__main__':
    unittest.main()
