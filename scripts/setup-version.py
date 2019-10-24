# -*- coding: utf-8 -*-

import os
import re
import time

with open(os.path.join(os.path.dirname(__file__), '..', 'walrus.py')) as file:
    for line in file:
        match = re.match(r"^__version__ = '(.*)'", line)
        if match is None:
            continue
        __version__ = match.groups()[0]
        break

context = list()
with open(os.path.join(os.path.dirname(__file__), '..', 'setup.py')) as file:
    for line in file:
        match = re.match(r"__version__ = '(.*)'", line)
        if match is None:
            context.append(line)
        else:
            context.append(f'__version__ = {__version__!r}\n')

with open(os.path.join(os.path.dirname(__file__), '..', 'setup.py'), 'w') as file:
    file.writelines(context)

context = list()
with open(os.path.join(os.path.dirname(__file__), '..', 'share', 'walrus.rst')) as file:
    for line in file:
        match = re.match(r":Version: (.*)", line)
        if match is None:
            match = re.match(r":Date: (.*)", line)
            if match is None:
                context.append(line)
            else:
                context.append(f":Date: {time.strftime('%B %d, %Y')}\n")
        else:
            context.append(f':Version: v{__version__}\n')

with open(os.path.join(os.path.dirname(__file__), '..', 'share', 'walrus.rst'), 'w') as file:
    file.writelines(context)
