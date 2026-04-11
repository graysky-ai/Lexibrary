"""StrEnum fixture: three string-valued members for enum extraction tests."""

from __future__ import annotations

from enum import StrEnum


class BuildStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    FAILED = "failed"
