secret = 1337


def foo():
    secret = 0

    def bar():
        nonlocal secret
        print('Encrypted secret:', pow((secret := 7331), 65537, 5185185188492592592609))

    bar()
    print('Secret:', secret)


foo()
print('Fake secret:', secret)
