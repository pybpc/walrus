x = 66
y = 77


class A:
    global z
    print(z := 888)
    x = 99
    print(x := x + 1)
    print(y := x + 10)
    print(y + 100)
    y = 999
    print(y)


print(x)
print(y)
print(z)
print(A.__dict__.get('z'))
