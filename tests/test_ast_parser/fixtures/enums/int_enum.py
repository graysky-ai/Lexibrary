"""IntEnum fixture: integer-valued members for enum value tests."""

from __future__ import annotations

from enum import IntEnum


class Priority(IntEnum):
    LOW = 0
    HIGH = 10
