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

file = io.BytesIO(b'\xde\xad\xbe\xef\xca\xfe\xba\xbe')

# A loop that can't be trivially rewritten using 2-arg iter()
while chunk := file.read(2):
    print('Got 2 bytes {!r}'.format(chunk))

file.close()

# Reuse a value that's expensive to compute
x = 10
numbers = [y := math.factorial(x), y**2, y**3]
print(numbers)
print(y)

# Share a subexpression between a comprehension filter clause and its output
filtered_data = [y for x in [20, -9, 8, -100] if (y := abs(x)) > 10]
print(filtered_data)
