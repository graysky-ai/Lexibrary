"""Cleanup logic for IWH signals -- TTL expiry and orphan detection."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from lexibrary.iwh.parser import parse_iwh
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR

IWH_FILENAME = ".iwh"


@dataclass
class CleanedSignal:
    """Record of a single IWH signal that was removed during cleanup."""

    source_dir: Path
    """Relative source directory the signal was mirroring."""

    scope: str
    """The IWH scope value (e.g. ``"incomplete"``, ``"blocked"``)."""

    reason: str
    """Why the signal was removed: ``"expired"`` or ``"orphaned"``."""


@dataclass
class CleanupResult:
    """Aggregate result of an ``iwh_cleanup`` run."""

    expired: list[CleanedSignal] = field(default_factory=list)
    """Signals removed because they exceeded the TTL."""

    orphaned: list[CleanedSignal] = field(default_factory=list)
    """Signals removed because their source directory no longer exists."""

    kept: int = 0
    """Count of signals that survived cleanup."""


def iwh_cleanup(
    project_root: Path,
    ttl_hours: int,
    *,
    remove_all: bool = False,
) -> CleanupResult:
    """Perform a single-pass TTL expiry and orphan detection on IWH signals.

    Walks ``.lexibrary/designs/`` for ``.iwh`` files and:

    1. Deletes signals whose ``created`` timestamp is older than *ttl_hours*
       from the current UTC time (or all signals when *remove_all* is True).
    2. Deletes signals whose corresponding source directory no longer exists
       under *project_root*.
    3. Deletes unparseable signals (treated as expired since their TTL cannot
       be validated).

    Args:
        project_root: Absolute path to the project root.
        ttl_hours: Maximum age in hours before a signal is expired.
        remove_all: When True, skip the TTL age check and treat all signals
            as expired. Orphan detection still runs.

    Returns:
        A :class:`CleanupResult` summarising what was removed and kept.
    """
    designs_dir = project_root / LEXIBRARY_DIR / DESIGNS_DIR
    if not designs_dir.is_dir():
        return CleanupResult()

    now = datetime.now(UTC)
    result = CleanupResult()

    for iwh_file_path in sorted(designs_dir.rglob(IWH_FILENAME)):
        # Derive the relative source directory from the mirror path.
        # e.g. .lexibrary/designs/src/auth/.iwh -> src/auth
        try:
            relative = iwh_file_path.parent.relative_to(designs_dir)
        except ValueError:
            continue

        parsed = parse_iwh(iwh_file_path)

        # Unparseable files are treated as expired -- they cannot be
        # validated for TTL so they are cleaned up.
        if parsed is None:
            _delete_iwh(iwh_file_path)
            result.expired.append(
                CleanedSignal(
                    source_dir=relative,
                    scope="unknown",
                    reason="expired",
                )
            )
            continue

        # Check orphan status: source directory must exist under project root.
        source_dir = project_root / relative
        if not source_dir.is_dir():
            _delete_iwh(iwh_file_path)
            result.orphaned.append(
                CleanedSignal(
                    source_dir=relative,
                    scope=parsed.scope,
                    reason="orphaned",
                )
            )
            continue

        # In remove_all mode, skip the TTL age check and treat as expired.
        if remove_all:
            _delete_iwh(iwh_file_path)
            result.expired.append(
                CleanedSignal(
                    source_dir=relative,
                    scope=parsed.scope,
                    reason="expired",
                )
            )
            continue

        # Check TTL expiry.
        created = parsed.created
        # Handle timezone-naive timestamps by treating them as UTC.
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)

        age_hours = (now - created).total_seconds() / 3600
        if age_hours > ttl_hours:
            _delete_iwh(iwh_file_path)
            result.expired.append(
                CleanedSignal(
                    source_dir=relative,
                    scope=parsed.scope,
                    reason="expired",
                )
            )
            continue

        # Signal is within TTL and has a valid source directory -- keep it.
        result.kept += 1

    return result


def _delete_iwh(path: Path) -> None:
    """Delete an IWH file, suppressing OS errors."""
    with contextlib.suppress(OSError):
        path.unlink()
