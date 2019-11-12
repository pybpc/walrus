x = 66
y = 77


class A:
    x = 99
    print(x := x + 1)
    print(y := x + 10)
    print(y + 100)


print(x)
print(y)
