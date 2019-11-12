# TODO: read through PEP 572 and finish this

# (y := f(x))  # Valid, though not recommended
# y0 = (y1 := f(x))  # Valid, though discouraged
# foo(x=(y := f(x)))  # Valid, though probably confusing
# def foo(answer=(p := 42)):  # Valid, though not great style
# def foo(answer: (p := 42) = 5):  # Valid, but probably never useful
# lambda: (x := 1) # Valid, but unlikely to be useful
# (x := lambda: 1) # Valid
# lambda line: (m := re.match(pattern, line)) and m.group(1) # Valid
# >>> f'{(x:=10)}'  # Valid, uses assignment expression
# '10'
# >>> x = 10
# >>> f'{x:=10}'    # Valid, passes '=10' to formatter
# '        10'
# [[(j := j) for i in range(5)] for j in range(5)] # INVALID
# [i := 0 for i, j in stuff]                       # INVALID
# [i+1 for i in (i := stuff)]                      # INVALID
# [False and (i := 0) for i, j in stuff]     # INVALID
# [i for i, j in stuff if True or (j := 1)]  # INVALID
