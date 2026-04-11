"""Nested function inside a method.

``Outer.method`` defines ``inner`` which calls ``helper()``. The nested
``inner`` must be captured as its own :class:`SymbolDefinition` and the
``helper()`` call must be attributed to ``inner``, not ``Outer.method``.
"""


def helper() -> int:
    return 1


class Outer:
    def method(self) -> int:
        def inner() -> int:
            return helper()

        return inner()
