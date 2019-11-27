import re

(lambda: ((x := 99), print(x)))()  # Valid, but unlikely to be useful
print(globals().get('x'))
(lambda: ([x := i ** 2 for i in range(10)], print(x)))()  # comprehension in lambda
print(globals().get('x'))
(x := lambda: 111)  # Valid
print(x())
print((lambda line: (m := re.match(r'(\d+) (\d+)', line)) and m.group(1))('347 467'))  # Valid
print(globals().get('m'))
