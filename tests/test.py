import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from walrus import get_parser
from walrus import main as main_func

# root path
ROOT = os.path.dirname(os.path.realpath(__file__))

# environs
os.environ['WALRUS_QUIET'] = 'true'
os.environ['WALRUS_ENCODING'] = 'utf-8'
os.environ['WALRUS_LINESEP'] = 'LF'


class TestWalrus(unittest.TestCase):
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
        with tempfile.TemporaryDirectory(prefix='walrus-test') as tmpdir:
            all_test_files = os.listdir(os.path.join(ROOT, 'sample'))

            for test_file in all_test_files:
                shutil.copy(os.path.join(ROOT, 'sample', test_file), tmpdir)

            main_func([tmpdir])

            for test_file in all_test_files:
                original_output = subprocess.check_output([sys.executable, os.path.join(ROOT, 'sample', test_file)])
                converted_output = subprocess.check_output([sys.executable, os.path.join(tmpdir, test_file)])
                self.assertEqual(original_output, converted_output, 'test case {!r} failed'.format(test_file))


if __name__ == '__main__':
    sys.exit(unittest.main())
