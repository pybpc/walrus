print(f'{(x := "awesome")!r:20}', x)


class A:
    locals = 555
    print(f'{(y := 666)}')
    print(y)
    print(f'''L1 -> {f"""L2 -> {f'L3 -> {f"L4 -> {(z := chr(77))!r} <- L4"} <- L3'} <- L2"""} <- L1''')
    print(z)
    print(f'see -> {"header " + f"{(w := chr(88))}" + " footer"} <- see')
    print(w)
    print(locals)


print(globals().get('y'))
print(globals().get('z'))
print(globals().get('w'))
print(callable(locals))
