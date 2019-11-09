z = 17
x = 12
y = -7
r = 555555555


def check_divisible(x):
    y = 7

    if r := pow(x, y, z):
        print('{} ^ {} is not divisible by {}, remainder is {}'.format(x, y, z, r))
    else:
        print('{} ^ {} is divisible by {}'.format(x, y, z))


check_divisible(7777)
check_divisible(8721)
print(x)
print(y)
print(r)
