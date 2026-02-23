"""Async token-bucket rate limiter for LLM API call throttling."""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Token-bucket rate limiter with async support.

    Enforces a configurable requests-per-minute limit by ensuring a minimum
    interval between successive calls. Uses asyncio.Lock for serialization.
    """

    def __init__(self, requests_per_minute: int = 50) -> None:
        self._interval = 60.0 / requests_per_minute
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until the next request slot is available."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if self._last_call > 0.0 and elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_call = time.monotonic()
