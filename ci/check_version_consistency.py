import os
import re
import subprocess  # nosec
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

source_code_version = subprocess.check_output([sys.executable,  # nosec
                                               os.path.join('scripts', 'find_version.py')],
                                              universal_newlines=True).strip()

man_page_src_file = os.path.join('share', 'walrus.rst')

with open(man_page_src_file, 'r', encoding='utf-8') as f:
    man_page_content = f.read()

m = re.search(r'(?m)^:Version: v(.*?)$', man_page_content)
if m is None:
    raise ValueError('version not found in man page')
man_page_version = m.group(1)
if man_page_version != source_code_version:
    raise ValueError('inconsistent versions in source code ({}) '
                     'and in man page ({})'.format(source_code_version, man_page_version))
