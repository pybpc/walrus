def foo1(x=(h1 := 1)):
    pass


print(h1)


def foo2(x: int = (h2 := 2)):
    pass


print(h2)


def foo3(x: (h3 := int)):
    pass


print(h3)


def foo4(x: (h4 := float) = 1.1): pass


print(h4)


def foo5(x=1) -> (h5 := complex):
    return x * 1j


print(h5)
