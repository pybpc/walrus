import io
import math
import re

pattern = re.compile(r'ba[rz]')

# Handle a matched regex
if (match := pattern.search('embark')) is not None:
    # Do something with match
    print('Found pattern in span {}.'.format(match.span()))
else:
    print('Pattern not found.')

# A loop that can't be trivially rewritten using 2-arg iter()
file = io.BytesIO(b'\xde\xad\xbe\xef\xca\xfe\xba\xbe')

while chunk := file.read(2):
    print('Got 2 bytes {!r}'.format(chunk))

file.close()

file = io.StringIO('help\nlist\nquit\n')

while (command := file.readline().strip()) != 'quit':
    print('You entered:', command)

file.close()

# Reuse a value that's expensive to compute
x = 10
numbers = [y := math.factorial(x), y**2, y**3]
print(numbers)
print(y)

# Share a subexpression between a comprehension filter clause and its output
filtered_data = [y for x in [20, -9, 8, -100] if (y := abs(x)) > 10]
print(filtered_data)

# Conveniently capture a "witness" for an any() expression, or a counterexample for all()
lines = ('s = "hello world"\n# Shout it out loud!\nprint(s)\n' + '# ' + 'A' * 100 + '\n').splitlines()

if any((comment := line).startswith('#') for line in lines):
    print('First comment:', comment)
else:
    print('There are no comments')

if all((nonblank := line).strip() == '' for line in lines):
    print('All lines are blank')
else:
    print('First non-blank line:', nonblank)

if any(len(longline := line) >= 100 for line in lines):
    print('Extremely long line:', longline)
else:
    print('No long lines.')

# Compute partial sums in a list comprehension
total = 0
partial_sums = [total := total + v for v in range(10)]
print('Partial Sums:', partial_sums)
print('Total:', total)
