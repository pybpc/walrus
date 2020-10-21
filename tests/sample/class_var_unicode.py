class A:
    print(Ç := 666)
    print(Ç)
    print(Ç)
    print(Ç := 777)
    print(Ç)


print(A.__dict__.get('Ç'))
print(A.Ç)


class Ḑ:
    class Ȩ:
        print(__Ģ := 888)
        print(__Ģ)
        print(_Ȩ__Ģ)
        print(_Ȩ__Ģ := 999)
        print(__Ģ)
    print(Ȩ.__dict__.get('__Ģ'))
    print(Ȩ._Ȩ__Ģ)
