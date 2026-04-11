"""Derived class that calls ``self.foo()`` (inherited) — drives the MRO walk."""

from __future__ import annotations

from pkg.base import Base


class Derived(Base):
    def bar(self) -> None:
        self.foo()
