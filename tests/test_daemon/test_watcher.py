"""Tests for the LexibraryEventHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, create_autospec

import pathspec
from watchdog.events import DirCreatedEvent, FileCreatedEvent, FileModifiedEvent

from lexibrary.daemon.debouncer import Debouncer
from lexibrary.daemon.watcher import LexibraryEventHandler
from lexibrary.ignore.matcher import IgnoreMatcher


def _make_handler(
    ignore_patterns: list[str] | None = None,
    root: Path | None = None,
) -> tuple[LexibraryEventHandler, MagicMock]:
    """Create handler with a mock debouncer and optional ignore patterns."""
    debouncer = create_autospec(Debouncer, instance=True)
    r = root or Path("/project")
    patterns = ignore_patterns or []
    config_spec = pathspec.PathSpec.from_lines("gitignore", patterns)
    matcher = IgnoreMatcher(r, config_spec, [])
    handler = LexibraryEventHandler(debouncer=debouncer, ignore_matcher=matcher)
    return handler, debouncer


def test_ignores_directory_events() -> None:
    """Directory creation/modification events are ignored."""
    handler, debouncer = _make_handler()
    event = DirCreatedEvent(src_path="/project/newdir")
    handler.on_any_event(event)
    debouncer.notify.assert_not_called()


def test_ignores_iandex_files() -> None:
    """Files starting with .aindex are ignored."""
    handler, debouncer = _make_handler()

    for name in [".aindex", ".aindex.bak", ".aindex_tmp"]:
        event = FileModifiedEvent(src_path=f"/project/{name}")
        handler.on_any_event(event)

    debouncer.notify.assert_not_called()


def test_ignores_cache_log_pid_files() -> None:
    """Internal files (cache, log, PID) are ignored."""
    handler, debouncer = _make_handler()

    for name in ["cache.json", "daemon.log", "daemon.pid"]:
        event = FileModifiedEvent(src_path=f"/project/{name}")
        handler.on_any_event(event)

    debouncer.notify.assert_not_called()


def test_notifies_debouncer_for_valid_changes() -> None:
    """Valid file changes notify the debouncer with the parent directory."""
    handler, debouncer = _make_handler()
    event = FileCreatedEvent(src_path="/project/src/main.py")
    handler.on_any_event(event)

    debouncer.notify.assert_called_once_with(Path("/project/src"))


def test_ignores_gitignored_files() -> None:
    """Files matching ignore patterns are not forwarded to the debouncer."""
    handler, debouncer = _make_handler(
        ignore_patterns=["*.pyc", "__pycache__/"],
        root=Path("/project"),
    )

    event = FileCreatedEvent(src_path="/project/module/__pycache__/foo.pyc")
    handler.on_any_event(event)

    debouncer.notify.assert_not_called()
