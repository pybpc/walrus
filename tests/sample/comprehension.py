comp1 = [x1 := x * x for x in range(10)]
print(comp1)
print(x1)
print(globals().get('x'))


def f2():
    comp2 = [x2 := x ** 3 for x in range(9)]
    print(comp2)
    print(x2)
    print(locals().get('x'))


def f3():
    global x3
    comp3 = [x3 := x ** 4 for x in range(8)]
    print(comp3)
    print(locals().get('x'))


def f4():
    x4 = 0
    def g4():
        nonlocal x4
        comp4 = [x4 := x ** 5 for x in range(7)]
        print(comp4)
        print(locals().get('x'))
    g4()
    print(x4)


def f5():
    comp5 = [[x5 := i for i in range(3)] for j in range(2)]
    print(comp5)
    print(x5)
    print(locals().get('i'))
    print(locals().get('j'))


f2()
print(globals().get('x'))
print(globals().get('x2'))
f3()
print(globals().get('x'))
print(globals().get('x3'))
f4()
print(globals().get('x'))
print(globals().get('x4'))
f5()
print(globals().get('i'))
print(globals().get('j'))
print(globals().get('x5'))
