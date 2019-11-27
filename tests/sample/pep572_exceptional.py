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
    (px, py, pz := (31, 32, 33))
except NameError:
    print('NameError')
else:
    print(px, py, pz)
