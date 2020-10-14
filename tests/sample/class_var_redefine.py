import os


class A:
    print('Redefine with variable')
    print(var := 21)
    var = 61
    print(var)
    print(vars()['var'])

    print('Redefine with function')
    print(func := 22)

    @staticmethod
    def func(var):
        print('foo called')
        return var

    print(type(func))

    print('Redefine with class')
    print(cls := 23)

    class cls:
        pass

    print(type(cls))

    print('Redefine with for Loop')
    print(loopvar := 24)

    for loopvar in range(64, 65):
        print(loopvar)

    [print(loopvar) for loopvar in range(74, 75)]  # loopvar should be local to this comprehension
    print(loopvar)

    print('Redefine with import')
    print(mod := 25)
    import sys as mod
    print(type(mod))
    print(item := 26)
    from sys import version as item
    print(isinstance(item, int))

    print('Redefine with with statement')
    print(ctx := 27)
    with open(os.devnull) as ctx:
        pass
    print(isinstance(ctx, int))

    print('Redefine with except statement')
    print(exc := 28)
    try:
        raise RuntimeError
    except RuntimeError as exc:
        print(type(exc))
    print(locals().get('exc'))

    print('Class A initialized')


print('var = {}'.format(A.var))
print('func is of type {}'.format(type(A.func)))
print('func execution returns: {}'.format(A.func(62)))
print('cls is of type: {}'.format(type(A.cls)))
print('loopvar = {}'.format(A.loopvar))
print('mod is of type {}'.format(type(A.mod)))
print('item is int? {}'.format(isinstance(A.item, int)))
print('ctx is int? {}'.format(isinstance(A.ctx, int)))
print('exc in A: {}'.format(A.__dict__.get('exc')))
