"""Class with __init__, foo, bar; foo calls self.bar() and helper()."""


def helper() -> int:
    return 42


class Example:
    def __init__(self) -> None:
        self.value = 0

    def foo(self) -> int:
        helper()
        return self.bar()

    def bar(self) -> int:
        return self.value
