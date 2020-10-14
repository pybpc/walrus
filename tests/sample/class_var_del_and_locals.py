x = 'outer'


class A:
    print(x := 666)  # new
    print(x)
    print(locals().get('x'))
    print(x := 777)  # update
    print(x)
    print(locals().get('x'))
    del x  # delete
    print(locals().get('x'))
    print(x := 888)  # recreate
    print(x)
    print(locals().get('x'))


print(x)
