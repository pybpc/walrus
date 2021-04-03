import os
import re
import shutil
import subprocess  # nosec
import sys
import time

os.chdir(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

version = subprocess.check_output([sys.executable,  # nosec
                                   os.path.join('scripts', 'find_version.py')],
                                  universal_newlines=True).strip()

man_page_src_file = os.path.join('share', 'walrus.rst')
man_page_dst_file = os.path.join('share', 'walrus.1')

with open(man_page_src_file, 'r', encoding='utf-8') as f:
    man_page_content = f.read()

man_page_content = re.sub(
    r'(?m)^:Version: (?:.*?)$',
    ':Version: v{}'.format(version).replace('\\', r'\\'),
    man_page_content, count=1
)
man_page_content = re.sub(
    r'(?m)^:Date: (?:.*?)$',
    ':Date: {}'.format(time.strftime('%B %d, %Y')).replace('\\', r'\\'),
    man_page_content, count=1
)

with open(man_page_src_file, 'w', encoding='utf-8') as f:
    f.write(man_page_content)

rst2man = shutil.which('rst2man.py')
if rst2man is None:
    raise RuntimeError('rst2man.py not found')
subprocess.check_call([sys.executable, rst2man, man_page_src_file, man_page_dst_file])  # nosec
