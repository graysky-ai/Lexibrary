"""PascalCase function — drives the non-class instantiation filter.

``Builder()`` here is a function call, not a class instantiation, so the
pass-3 builder's ``instantiates`` symbol_type check must skip it rather
than emit an edge pointing at a function.
"""

from __future__ import annotations


def Builder() -> None:
    pass


def main() -> None:
    Builder()
