bar = 111


def foo():
    bar = 437
    lol = 0
    class A:
        @staticmethod
        def baz():
            nonlocal bar
            print(bar := 777)
        nonlocal lol
        print(lol := 999)
    A.baz()
    print(bar)
    print(lol)
    print(A.__dict__.get('lol'))


foo()
print(bar)
