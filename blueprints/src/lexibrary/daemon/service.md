# daemon/service

**Summary:** `DaemonService` orchestrates library maintenance via three entry points: `run_once` (single sweep), `run_watch` (periodic sweeps), and `run_watchdog` (deprecated real-time file watching). Uses the archivist pipeline (`update_project`) instead of the retired crawler engine.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `DaemonService` | class | Top-level daemon orchestrator; constructor accepts `root: Path` |
| `DaemonService.run_once` | `() -> None` | Run a single project update sweep, respecting `sweep_skip_if_unchanged` |
| `DaemonService.run_watch` | `() -> None` | Run periodic sweeps in the foreground until interrupted (SIGTERM/SIGINT) |
| `DaemonService.run_watchdog` | `() -> None` | Deprecated real-time file watchdog; requires `watchdog_enabled: true` in config |
| `DaemonService.stop` | `() -> None` | Gracefully stop all daemon components (sweep, observer, PID file) |
| `_has_changes` | `(root: Path, last_sweep: float) -> bool` | Fast mtime scan via `os.scandir()`; skips `.lexibrary/`; returns `True` on first newer file or if `last_sweep == 0.0` |

## Dependencies

- `lexibrarian.archivist.pipeline` -- `update_project`
- `lexibrarian.archivist.service` -- `ArchivistService`
- `lexibrarian.config.loader` -- `load_config`
- `lexibrarian.config.schema` -- `LexibraryConfig`
- `lexibrarian.daemon.logging` -- `setup_daemon_logging`
- `lexibrarian.daemon.scheduler` -- `PeriodicSweep`
- `lexibrarian.ignore` -- `create_ignore_matcher`
- `lexibrarian.llm.rate_limiter` -- `RateLimiter`
- `lexibrarian.utils.paths` -- `LEXIBRARY_DIR`
- `lexibrarian.daemon.debouncer` -- `Debouncer` (lazy, watchdog only)
- `lexibrarian.daemon.watcher` -- `LexibrarianEventHandler` (lazy, watchdog only)
- `watchdog.observers` -- `Observer` (lazy, watchdog only)

## Dependents

- `lexibrarian.cli.lexictl_app` -- `sweep` command calls `run_once` / `run_watch`; `daemon` command calls `run_watchdog`

## Key Concepts

- Three entry points replace the old single `start()` method:
  - `run_once()` -- single sweep then exit; respects `sweep_skip_if_unchanged`
  - `run_watch()` -- periodic sweeps via `PeriodicSweep`; blocks on `_shutdown_event`
  - `run_watchdog()` -- deprecated; requires `daemon.watchdog_enabled: true`; lazy-imports watchdog
- `_has_changes()` does a fast recursive mtime scan with `os.scandir()`, skipping `.lexibrary/`
- Sweep callback uses `asyncio.run(update_project(...))` via `ArchivistService` + `RateLimiter`
- PID file (`<root>/.lexibrarian.pid`) written only in watchdog mode; removed on `stop()`
- SIGTERM/SIGINT both trigger `_shutdown_event.set()` for graceful shutdown
- Watchdog imports are lazy -- `run_once` and `run_watch` work without the `watchdog` package installed
- `_current_time()` is extracted as a function for testability

## Dragons

- `run_watchdog()` raises `ImportError` if `watchdog` package is not installed
- All three entry points call `setup_daemon_logging()` to configure rotating file logging
- `_periodic_callback` checks `sweep_skip_if_unchanged` before each sweep to avoid unnecessary LLM calls
