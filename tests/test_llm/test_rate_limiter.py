"""Tests for the async token-bucket rate limiter."""

from __future__ import annotations

import asyncio
import time

import pytest

from lexibrary.llm.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_first_acquire_is_immediate() -> None:
    """First acquire on a fresh RateLimiter should return without delay."""
    limiter = RateLimiter(requests_per_minute=60)
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1


@pytest.mark.asyncio
async def test_rapid_calls_are_throttled() -> None:
    """Two rapid acquires should enforce the minimum interval."""
    rpm = 60  # 1 second interval
    limiter = RateLimiter(requests_per_minute=rpm)
    expected_interval = 60.0 / rpm

    await limiter.acquire()
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start

    assert elapsed >= expected_interval * 0.9  # allow 10% tolerance


@pytest.mark.asyncio
async def test_concurrent_acquires_are_serialized() -> None:
    """Multiple concurrent acquires should be serialized via the lock."""
    rpm = 120  # 0.5 second interval
    limiter = RateLimiter(requests_per_minute=rpm)
    expected_interval = 60.0 / rpm

    timestamps: list[float] = []

    async def acquire_and_record() -> None:
        await limiter.acquire()
        timestamps.append(time.monotonic())

    # Launch 3 concurrent acquires
    await asyncio.gather(
        acquire_and_record(),
        acquire_and_record(),
        acquire_and_record(),
    )

    assert len(timestamps) == 3
    timestamps.sort()

    # Each successive call should be at least interval apart
    for i in range(1, len(timestamps)):
        gap = timestamps[i] - timestamps[i - 1]
        assert gap >= expected_interval * 0.9  # allow 10% tolerance


@pytest.mark.asyncio
async def test_default_rpm() -> None:
    """Default RateLimiter should use 50 RPM (1.2s interval)."""
    limiter = RateLimiter()
    expected_interval = 60.0 / 50
    assert abs(limiter._interval - expected_interval) < 0.001


@pytest.mark.asyncio
async def test_custom_rpm() -> None:
    """Custom RPM should set the correct interval."""
    limiter = RateLimiter(requests_per_minute=120)
    assert abs(limiter._interval - 0.5) < 0.001
