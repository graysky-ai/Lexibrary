"""Tests for the PeriodicSweep scheduler."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from lexibrary.daemon.scheduler import PeriodicSweep


def test_sweep_fires_on_schedule() -> None:
    """Sweep callback fires after the configured interval."""
    fired = threading.Event()
    callback = MagicMock(side_effect=lambda: fired.set())

    sweep = PeriodicSweep(interval=0.05, callback=callback)
    sweep.start()

    assert fired.wait(timeout=2.0)
    sweep.stop()
    callback.assert_called()


def test_stop_prevents_further_callbacks() -> None:
    """Stopping the sweep prevents future callbacks from firing."""
    callback = MagicMock()

    sweep = PeriodicSweep(interval=0.05, callback=callback)
    sweep.start()
    sweep.stop()

    time.sleep(0.2)
    callback.assert_not_called()


def test_sweep_reschedules_after_completion() -> None:
    """After a sweep completes, the next one is scheduled."""
    call_count = 0
    second_fired = threading.Event()

    def callback() -> None:
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            second_fired.set()

    sweep = PeriodicSweep(interval=0.05, callback=callback)
    sweep.start()

    assert second_fired.wait(timeout=2.0)
    sweep.stop()
    assert call_count >= 2


def test_callback_exception_is_contained() -> None:
    """Exception in callback doesn't prevent future sweeps."""
    call_count = 0
    second_fired = threading.Event()

    def failing_then_ok() -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")
        second_fired.set()

    sweep = PeriodicSweep(interval=0.05, callback=failing_then_ok)
    sweep.start()

    assert second_fired.wait(timeout=2.0)
    sweep.stop()
    assert call_count >= 2
