# daemon/debouncer

**Summary:** Thread-safe debouncer that coalesces rapid filesystem change notifications into a single callback after a configurable quiet period.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `Debouncer` | class | Collects changed directories and fires callback after `delay` seconds of quiet |
| `Debouncer.__init__` | `(delay: float, callback: Callable[[set[Path]], None])` | Configure delay and callback |
| `Debouncer.notify` | `(directory: Path) -> None` | Add directory to pending set; reset timer |
| `Debouncer.cancel` | `() -> None` | Cancel pending timer and clear accumulated directories |

## Dependents

- `lexibrarian.daemon.service` — creates instance and passes as debouncer callback target
- `lexibrarian.daemon.watcher` — calls `notify()` on valid events

## Key Concepts

- Each `notify()` call cancels and restarts the timer — only fires after the quiet period
- Thread-safe via `threading.Lock`; timer thread is marked daemon so it doesn't block process exit
