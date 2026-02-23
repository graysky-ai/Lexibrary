"""Per-directory write lock manager for serialising .aindex writes."""

from __future__ import annotations

import threading
from pathlib import Path


class DirectoryLockManager:
    """Provides per-directory ``threading.Lock`` instances.

    Under the sequential MVP processing model the locks are effectively
    no-ops (no contention), but they ensure correctness when async /
    concurrent processing is added later.

    Thread-safe: concurrent calls to :meth:`get_lock` for the same
    directory will always return the same ``Lock`` instance.
    """

    def __init__(self) -> None:
        self._locks: dict[Path, threading.Lock] = {}
        self._guard = threading.Lock()

    def get_lock(self, directory: Path) -> threading.Lock:
        """Return the lock associated with *directory*.

        If no lock exists yet for the resolved path, one is created
        atomically.

        Args:
            directory: Directory path to get a lock for.

        Returns:
            A ``threading.Lock`` bound to *directory*.
        """
        resolved = directory.resolve()
        with self._guard:
            if resolved not in self._locks:
                self._locks[resolved] = threading.Lock()
            return self._locks[resolved]
