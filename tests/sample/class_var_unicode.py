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
        print(Ģ := 888)
        print(Ģ)
        print(Ģ)
        print(Ģ := 999)
        print(Ģ)
    print(Ȩ.__dict__.get('Ģ'))
    print(Ȩ.Ģ)
