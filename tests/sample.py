# -*- coding: utf-8 -*-

import re

string = 'test sample'

# if (match := re.match(r'test', string)) is not None:
#     print(match)

t = (match := re.match(r'test', string))
print(t)
