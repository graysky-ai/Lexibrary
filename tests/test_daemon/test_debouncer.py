"""Tests for the Debouncer class."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

from lexibrary.daemon.debouncer import Debouncer


def test_callback_fires_after_delay() -> None:
    """Callback fires once after the debounce delay with the notified directory."""
    fired = threading.Event()
    received: list[set[Path]] = []

    def callback(dirs: set[Path]) -> None:
        received.append(dirs)
        fired.set()

    debouncer = Debouncer(delay=0.05, callback=callback)
    debouncer.notify(Path("/a"))

    assert fired.wait(timeout=2.0)
    assert received == [{Path("/a")}]


def test_rapid_events_reset_timer() -> None:
    """Rapid notifications reset the timer; callback fires once after quiet period."""
    fired = threading.Event()
    received: list[set[Path]] = []

    def callback(dirs: set[Path]) -> None:
        received.append(dirs)
        fired.set()

    debouncer = Debouncer(delay=0.1, callback=callback)

    # Send rapid notifications
    for _ in range(5):
        debouncer.notify(Path("/a"))
        time.sleep(0.02)

    assert fired.wait(timeout=2.0)
    assert len(received) == 1
    assert received[0] == {Path("/a")}


def test_multiple_directories_accumulated() -> None:
    """Multiple unique directories are accumulated and passed to callback."""
    fired = threading.Event()
    received: list[set[Path]] = []

    def callback(dirs: set[Path]) -> None:
        received.append(dirs)
        fired.set()

    debouncer = Debouncer(delay=0.05, callback=callback)
    debouncer.notify(Path("/a"))
    debouncer.notify(Path("/b"))
    debouncer.notify(Path("/c"))

    assert fired.wait(timeout=2.0)
    assert received == [{Path("/a"), Path("/b"), Path("/c")}]


def test_cancel_prevents_callback() -> None:
    """Calling cancel() prevents the callback from firing."""
    callback = MagicMock()
    debouncer = Debouncer(delay=0.05, callback=callback)

    debouncer.notify(Path("/a"))
    debouncer.cancel()

    time.sleep(0.15)
    callback.assert_not_called()


def test_callback_exception_is_contained() -> None:
    """Exception in callback is caught; debouncer remains operational."""
    call_count = 0
    second_fired = threading.Event()

    def failing_then_ok(dirs: set[Path]) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")
        second_fired.set()

    debouncer = Debouncer(delay=0.05, callback=failing_then_ok)

    # First call raises
    debouncer.notify(Path("/a"))
    time.sleep(0.15)
    assert call_count == 1

    # Second call should still work
    debouncer.notify(Path("/b"))
    assert second_fired.wait(timeout=2.0)
    assert call_count == 2
