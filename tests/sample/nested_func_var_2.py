def foo():
    x = 1
    def bar():
        x = 2
        def baz():
            nonlocal x
            print(x := 777)
        baz()
        print(x)
    bar()
    print(x)
foo()


def foo():
    (x := 1)
    def bar():
        nonlocal x
        (x := 2)
        def baz():
            nonlocal x
            (x := 3)
        baz()
        print(x)
    bar()
    print(x)
foo()
