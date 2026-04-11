"""Shared filter helpers for curator collect-phase functions.

Extracted from :mod:`lexibrary.curator.coordinator` so that the three
collectors that honour scope isolation (`_collect_staleness`,
`_collect_comments`, `_collect_validation`) can share a single source of
truth for the "skip this path" predicate.

A path is considered skippable when it is either:

* present in the set of uncommitted source files (so the curator does not
  fight an in-flight edit), or
* located inside a directory that currently has an active IWH signal
  (where a previous agent has already recorded something worth preserving).
"""

from __future__ import annotations

from pathlib import Path


def _should_skip_path(
    path: Path,
    uncommitted: set[Path],
    active_iwh: set[Path],
) -> bool:
    """Return ``True`` if ``path`` should be skipped by a collect function.

    Parameters
    ----------
    path:
        The source path under consideration.
    uncommitted:
        The set of source files with uncommitted git changes.
    active_iwh:
        The set of source directories with active (non-stale) IWH signals.

    Returns
    -------
    bool
        ``True`` if the path is uncommitted or lies inside an active IWH
        directory; ``False`` otherwise.
    """
    if path in uncommitted:
        return True
    return any(path.is_relative_to(d) for d in active_iwh)
