a = 42


def f():
    # `a` is local to `f`, but remains unbound
    # until the caller executes this genexp:
    yield ((a := i) for i in range(3))
    yield lambda: a + 100
    print('done')
    try:
        print('`a` is bound to {}'.format(a))
        assert False
    except UnboundLocalError:
        print('`a` is not yet bound')


results = list(f())
print(list(map(type, results)))
print(list(results[0]))
print(results[1]())
print(a)
