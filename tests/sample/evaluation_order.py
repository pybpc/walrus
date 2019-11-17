def called(expr):
    print('{} is evaluated'.format(expr))
    return expr


print([called(1), a := called(2)])
print(a)
