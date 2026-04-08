"""Sweep service -- change detection and sweep orchestration.

Extracted from :mod:`lexibrary.cli.lexictl_app` so the domain logic
(file-change detection, single-sweep execution, watch-loop orchestration)
lives in a testable service module while the CLI handler remains a thin
delegation layer.
"""

from __future__ import annotations

import asyncio
import os as _os
import threading
import time as _time
from collections.abc import Callable
from pathlib import Path

from lexibrary.archivist.pipeline import UpdateStats, update_project
from lexibrary.archivist.service import ArchivistService
from lexibrary.config.schema import LexibraryConfig
from lexibrary.llm.client_registry import build_client_registry
from lexibrary.llm.rate_limiter import RateLimiter
from lexibrary.utils.paths import LEXIBRARY_DIR


def has_changes(
    root: Path,
    last_sweep: float,
    lexibrary_dir: str = LEXIBRARY_DIR,
) -> bool:
    """Check whether any file under *root* has mtime newer than *last_sweep*.

    Uses ``os.scandir()`` for a fast stat walk.  Returns ``True`` on the
    first file found with a newer mtime (short-circuit).  Skips the
    *lexibrary_dir* directory to avoid self-triggered loops.

    If *last_sweep* is ``0.0`` (first run), always returns ``True``.
    Returns ``True`` on ``OSError`` (fail-open).
    """
    if last_sweep == 0.0:
        return True

    lexibrary_abs = (root / lexibrary_dir).resolve()

    def _scan(directory: Path) -> bool:
        try:
            with _os.scandir(directory) as it:
                for entry in it:
                    entry_path = Path(entry.path).resolve()

                    if entry.is_dir(follow_symlinks=False):
                        if entry_path == lexibrary_abs:
                            continue
                        if _scan(entry_path):
                            return True
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            if entry.stat().st_mtime > last_sweep:
                                return True
                        except OSError:
                            continue
        except OSError:
            pass
        return False

    return _scan(root)


def run_single_sweep(
    project_root: Path,
    config: LexibraryConfig,
) -> UpdateStats:
    """Execute one ``update_project()`` call and return the stats.

    Sets up a :class:`~lexibrary.llm.rate_limiter.RateLimiter`,
    builds the client registry, creates an
    :class:`~lexibrary.archivist.service.ArchivistService`, and runs
    the pipeline synchronously via :func:`asyncio.run`.

    Parameters
    ----------
    project_root:
        The project root directory.
    config:
        Loaded Lexibrary configuration.

    Returns
    -------
    UpdateStats
        Accumulated pipeline statistics for the sweep.
    """
    rate_limiter = RateLimiter()
    registry = build_client_registry(config)
    archivist = ArchivistService(rate_limiter=rate_limiter, client_registry=registry)
    return asyncio.run(update_project(project_root, config, archivist))


def run_sweep_watch(
    project_root: Path,
    config: LexibraryConfig,
    *,
    interval: float,
    skip_unchanged: bool,
    on_complete: Callable[[UpdateStats], None],
    on_skip: Callable[[], None],
    on_error: Callable[[Exception], None],
    shutdown_event: threading.Event,
) -> None:
    """Run the sweep watch loop until *shutdown_event* is set.

    On each iteration: if *skip_unchanged* and no changes are detected,
    calls *on_skip*.  Otherwise attempts :func:`run_single_sweep` and
    calls *on_complete* with the resulting stats.  On failure, calls
    *on_error* with the exception.  Waits on *shutdown_event* with
    ``timeout=interval`` between iterations.

    Signal handler setup (SIGTERM/SIGINT) is **not** handled here --
    it is CLI-specific and stays in the CLI handler.

    Parameters
    ----------
    project_root:
        The project root directory.
    config:
        Loaded Lexibrary configuration.
    interval:
        Seconds between sweep iterations.
    skip_unchanged:
        When ``True``, skip sweeps if no files changed since last sweep.
    on_complete:
        Called with :class:`UpdateStats` after a successful sweep.
    on_skip:
        Called when a sweep is skipped due to no changes.
    on_error:
        Called with the exception when a sweep fails.
    shutdown_event:
        :class:`threading.Event` that signals the loop to stop.
    """
    last_sweep: float = 0.0

    while not shutdown_event.is_set():
        if skip_unchanged and not has_changes(project_root, last_sweep):
            on_skip()
        else:
            try:
                stats = run_single_sweep(project_root, config)
                last_sweep = _time.time()
                on_complete(stats)
            except Exception as exc:
                on_error(exc)

        shutdown_event.wait(timeout=interval)
