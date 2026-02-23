# daemon/scheduler

**Summary:** Periodic sweep scheduler that fires a no-argument callback at a fixed interval as a safety net for missed watchdog events.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `PeriodicSweep` | class | Fires `callback()` every `interval` seconds |
| `PeriodicSweep.__init__` | `(interval: float, callback: Callable[[], None])` | Configure interval and callback |
| `PeriodicSweep.start` | `() -> None` | Schedule the first sweep |
| `PeriodicSweep.stop` | `() -> None` | Cancel any pending timer |

## Dependents

- `lexibrarian.daemon.service` — creates instance; callback runs `full_crawl`

## Key Concepts

- Each sweep reschedules the next one in the `finally` block (interval starts after completion, not at start)
- Timer thread is daemon so process can exit cleanly
