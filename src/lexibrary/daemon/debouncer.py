"""Debouncer for coalescing file system events into batched callbacks."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class Debouncer:
    """Coalesces rapid file change notifications into a single callback.

    Collects affected directories and fires the callback after a configurable
    quiet period. Each new notification resets the timer. Thread-safe.
    """

    def __init__(
        self,
        delay: float,
        callback: Callable[[set[Path]], None],
    ) -> None:
        self._delay = delay
        self._callback = callback
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._pending: set[Path] = set()

    def notify(self, directory: Path) -> None:
        """Register a changed directory, resetting the debounce timer."""
        with self._lock:
            self._pending.add(directory)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        """Fire the callback with accumulated directories."""
        with self._lock:
            dirs = self._pending.copy()
            self._pending.clear()
            self._timer = None

        if not dirs:
            return

        try:
            self._callback(dirs)
        except Exception:
            logger.exception("Debouncer callback failed")

    def cancel(self) -> None:
        """Cancel any pending timer and discard accumulated directories."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending.clear()
