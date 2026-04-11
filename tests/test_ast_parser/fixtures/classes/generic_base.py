"""Generic base fixture: ``Generic[T]`` should collapse to ``Generic``."""

from typing import Generic, TypeVar

T = TypeVar("T")


class Foo(Generic[T]):
    pass
