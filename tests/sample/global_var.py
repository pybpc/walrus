a = 6
print(b := a * a)
print(b + 1)

for _ in range(2):
    c = 1
    print(c := 2)


for x in (6, 0):
    if a and (d := x):
        print(d)
    elif e := 7:
        print(e)
    else:
        print('Nope :=')
