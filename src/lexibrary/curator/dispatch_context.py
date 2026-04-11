"""Shared dispatch context for curator sub-agent handlers.

Defines the :class:`DispatchContext` dataclass that carries the
subset of coordinator state each extracted dispatch function needs.
Passing a single ``ctx`` object keeps the module-level dispatch
functions free of hidden coupling to the ``Coordinator`` class and
makes them trivial to test in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.errors import ErrorSummary


@dataclass
class DispatchContext:
    """State bundle passed to every extracted dispatch function.

    The curator coordinator builds one of these per dispatch cycle (via
    :meth:`Coordinator._ctx`) and hands it to the public dispatch
    functions defined in sibling modules.  Handlers must never mutate
    ``project_root``, ``config``, or ``lexibrary_dir``; ``summary``
    may be mutated to record errors.
    """

    project_root: Path
    config: LexibraryConfig
    summary: ErrorSummary
    lexibrary_dir: Path
    dry_run: bool
    uncommitted: set[Path]
    active_iwh: set[Path]
