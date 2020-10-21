class A:
    print(__x := 666)
    print(__x)
    print(_A__x)
    print(_A__x := 777)
    print(__x)


print(A.__dict__.get('__x'))
print(A._A__x)


class B:
    class C:
        print(__y := 888)
        print(__y)
        print(_C__y)
        print(_C__y := 999)
        print(__y)
    print(C.__dict__.get('__y'))
    print(C._C__y)
