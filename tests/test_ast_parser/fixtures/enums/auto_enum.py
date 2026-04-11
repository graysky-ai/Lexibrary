"""Auto-valued Enum fixture: ``auto()`` members yield value=None."""

from __future__ import annotations

from enum import Enum, auto


class Mode(Enum):
    READ = auto()
    WRITE = auto()
