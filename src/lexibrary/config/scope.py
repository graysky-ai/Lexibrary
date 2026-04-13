"""Owning-root resolution for multi-root scope configuration.

This module exposes a single helper, :func:`find_owning_root`, that every
ownership decision in the codebase funnels through. Concentrating "is this
file inside any declared root?" in one place is the single biggest risk
reducer for the multi-root migration — a bug here propagates to every caller
(archivist, validator, conventions, lookup, bootstrap, CLI gating).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from lexibrary.config.schema import ScopeRoot


def find_owning_root(
    path: Path,
    roots: Iterable[ScopeRoot],
    project_root: Path,
) -> ScopeRoot | None:
    """Return the first declared :class:`ScopeRoot` that owns ``path``.

    First-match wins: iteration follows the order the user declared the roots
    in, so callers can predict precedence by reading the config.

    Both ``path`` and each root's ``path`` are resolved absolutely (via
    ``(project_root / entry).resolve()``) before comparison. Existence of the
    root on disk is not required here — existence filtering lives in
    :meth:`LexibraryConfig.resolved_scope_roots`. This split lets ``lookup``
    and ``impact`` answer ownership questions for roots that the user has
    declared but not yet materialised (e.g. sparse checkouts).

    Returns ``None`` when no declared root contains ``path``.
    """

    project_root_abs = project_root.resolve()
    path_abs = path.resolve() if path.is_absolute() else (project_root_abs / path).resolve()

    for root in roots:
        root_abs = (project_root_abs / root.path).resolve()
        if path_abs == root_abs or path_abs.is_relative_to(root_abs):
            return root

    return None
