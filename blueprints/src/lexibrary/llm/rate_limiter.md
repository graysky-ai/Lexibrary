# llm/rate_limiter

**Summary:** Async token-bucket rate limiter enforcing a minimum interval between LLM API calls to stay within provider RPM limits.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `RateLimiter` | class | Serializes LLM calls to a configurable requests-per-minute rate |
| `RateLimiter.__init__` | `(requests_per_minute: int = 50)` | Compute interval: `60 / rpm` |
| `RateLimiter.acquire` | `async () -> None` | Wait until next slot; serialized via `asyncio.Lock` |

## Dependents

- `lexibrarian.llm.service` — calls `await self._rate_limiter.acquire()` before every LLM call
- `lexibrarian.llm.factory` — creates a `RateLimiter()` with default 50 RPM

## Key Concepts

- Uses `time.monotonic()` for wall-clock interval; `asyncio.Lock` prevents concurrent callers from bypassing the limiter
