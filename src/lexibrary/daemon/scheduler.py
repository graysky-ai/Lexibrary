"""Periodic sweep scheduler for safety-net full crawls."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class PeriodicSweep:
    """Fires a callback at regular intervals as a safety net for missed events.

    After each callback completes (or fails), the next sweep is scheduled
    after another full interval.
    """

    def __init__(
        self,
        interval: float,
        callback: Callable[[], None],
    ) -> None:
        self._interval = interval
        self._callback = callback
        self._timer: threading.Timer | None = None
        self._stopped = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the periodic sweep schedule."""
        with self._lock:
            self._stopped = False
            self._schedule_next()

    def stop(self) -> None:
        """Stop the periodic sweep and cancel any pending timer."""
        with self._lock:
            self._stopped = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _schedule_next(self) -> None:
        """Schedule the next sweep after the configured interval."""
        if self._stopped:
            return
        self._timer = threading.Timer(self._interval, self._run_sweep)
        self._timer.daemon = True
        self._timer.start()

    def _run_sweep(self) -> None:
        """Execute the sweep callback and reschedule."""
        try:
            self._callback()
        except Exception:
            logger.exception("Periodic sweep callback failed")
        finally:
            with self._lock:
                self._schedule_next()
