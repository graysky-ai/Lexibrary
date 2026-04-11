"""Instantiation site — drives the ``instantiates`` edge assertion."""

from __future__ import annotations

from pkg.derived import Derived


def main() -> None:
    d = Derived()
    d.bar()
