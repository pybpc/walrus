bar = 111


def foo():
    bar = 437
    class A:
        @staticmethod
        def baz():
            nonlocal bar
            print(bar := 777)
    A.baz()
    print(bar)


foo()
print(bar)
