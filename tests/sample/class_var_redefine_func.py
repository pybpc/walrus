class A:
    print(foo := 233)

    def foo(self):
        print('foo called')
        return 666


print(type(A.foo))
print(A().foo())
