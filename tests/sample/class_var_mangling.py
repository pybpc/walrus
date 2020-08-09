class A:
    print(__x := 666)
    print(__x)
    print(_A__x)
    print(_A__x := 777)
    print(__x)


print(A.__dict__.get('__x'))
print(A._A__x)
