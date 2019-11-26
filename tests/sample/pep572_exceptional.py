import re

(y := 1)  # Valid, though not recommended
print(y)
y0 = (y1 := 2)  # Valid, though discouraged
print(y0, y1)
print(z1 := -1, z2 := -2)  # Valid
print(z1, z2)
print(dict(x=(z := 3)))  # Valid, though probably confusing
print(z)


def foo(answer=(p := 42)):  # Valid, though not great style
    print(answer)

print(p)
foo()


def bar(answer: (q := 24) = 5):  # Valid, but probably never useful
    print(answer)

print(q)
bar()

(lambda: ((x := 99), print(x)))()  # Valid, but unlikely to be useful
print(globals().get('x'))
(lambda: ([x := i ** 2 for i in range(10)], print(x)))()  # comprehension in lambda
print(globals().get('x'))

(x := lambda: 111)  # Valid
print(x())
del x

print((lambda line: (m := re.match(r'(\d+) (\d+)', line)) and m.group(1))('347 467'))  # Valid

print(f'{(x:=10)}')  # Valid, uses assignment expression
print(x)
print(f'{x:=5}')  # Valid, passes '=5' to formatter
print(x)

(z := (y := (x := 0)))
print(x, y, z)
print((x := 11, 22))  # Sets x to 11
print(x)

print(loc := (33, 44))
print(loc)
data = [15, 16, 17]
print(info := (13, 14, *data))
print(info)

try:
    print(px, py, pz := (31, 32, 33))
except NameError:
    print('NameError')
