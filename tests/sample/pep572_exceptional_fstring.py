print(f'{(x:=10)}')  # Valid, uses assignment expression
print(x)
print(f'{x:=5}')  # Valid, passes '=5' to formatter
print(x)
