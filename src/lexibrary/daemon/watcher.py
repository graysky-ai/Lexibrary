"""Watchdog event handler for filtering and forwarding file system events."""

from __future__ import annotations

import logging
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler

from lexibrary.daemon.debouncer import Debouncer
from lexibrary.ignore.matcher import IgnoreMatcher

logger = logging.getLogger(__name__)

# Internal files that should never trigger re-indexing.
# Daemon runtime files now live inside .lexibrary/ (daemon.log, daemon.pid, cache.json).
# The .lexibrary/ directory is already excluded by the ignore matcher, so these
# filenames are kept as a belt-and-suspenders guard for direct name matches.
_INTERNAL_FILES = frozenset(
    {
        "cache.json",
        "daemon.log",
        "daemon.pid",
    }
)


class LexibraryEventHandler(FileSystemEventHandler):
    """Filters file system events and notifies the debouncer for valid changes.

    Ignores:
    - Directory events (only file changes matter)
    - .aindex files (prevents infinite re-index loops)
    - Internal files (cache, log, PID)
    - Files matching ignore patterns (gitignore + config)
    """

    def __init__(
        self,
        debouncer: Debouncer,
        ignore_matcher: IgnoreMatcher,
    ) -> None:
        super().__init__()
        self._debouncer = debouncer
        self._ignore_matcher = ignore_matcher

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Process any file system event, applying filters."""
        # Ignore directory events
        if event.is_directory:
            return

        src_path = Path(str(event.src_path))
        name = src_path.name

        # Ignore .aindex files (prefix match)
        if name.startswith(".aindex"):
            return

        # Ignore internal files
        if name in _INTERNAL_FILES:
            return

        # Ignore files matching ignore patterns
        if self._ignore_matcher.is_ignored(src_path):
            return

        # Notify debouncer with the parent directory
        parent = src_path.parent
        logger.debug("File event: %s -> notifying debouncer for %s", event.src_path, parent)
        self._debouncer.notify(parent)
