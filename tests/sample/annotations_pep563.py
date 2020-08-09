from __future__ import annotations

import typing


def foo() -> (a := int):
    return 1


print(foo())
print(type(foo.__annotations__['return']))
print(globals().get('a'))
print(typing.get_type_hints(foo))
print(a)
