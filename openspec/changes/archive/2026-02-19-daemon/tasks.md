## 1. Setup & Dependencies

- [x] 1.1 Add `watchdog` dependency to `pyproject.toml` with bounded version range
- [x] 1.2 Run `uv sync` to install the new dependency
- [x] 1.3 Create the `src/lexibrary/daemon/` package directory with `__init__.py`

## 2. Debouncer

- [x] 2.1 Implement `Debouncer` class in `src/lexibrary/daemon/debouncer.py` with `notify()`, `_fire()`, and `cancel()` methods using `threading.Timer` and lock-based thread safety
- [x] 2.2 Write tests in `tests/test_daemon/test_debouncer.py`: callback fires after delay, rapid events reset timer, multiple directories accumulated, cancel prevents callback, callback exception is contained

## 3. Periodic Sweep Scheduler

- [x] 3.1 Implement `PeriodicSweep` class in `src/lexibrary/daemon/scheduler.py` with `start()`, `stop()`, `_schedule_next()`, and `_run_sweep()` methods
- [x] 3.2 Write tests in `tests/test_daemon/test_scheduler.py`: sweep fires on schedule, stop prevents further callbacks, sweep reschedules after completion, callback exception is contained

## 4. File Watcher Event Handler

- [x] 4.1 Implement `LexibraryEventHandler` class in `src/lexibrary/daemon/watcher.py` extending `FileSystemEventHandler` with filtering logic for directory events, `.aindex` files, internal files, and ignored files
- [x] 4.2 Write tests in `tests/test_daemon/test_watcher.py`: ignores directory events, ignores `.aindex` files, ignores cache/log/pid files, notifies debouncer for valid changes, ignores gitignored files

## 5. Daemon Service

- [x] 5.1 Implement `DaemonService` class in `src/lexibrary/daemon/service.py` with `start()`, `stop()`, signal handlers, PID file management, `_incremental_reindex()`, and `_full_sweep()` methods
- [x] 5.2 Export `DaemonService` from `src/lexibrary/daemon/__init__.py`
- [x] 5.3 Write tests in `tests/test_daemon/test_service.py`: PID file created on start, PID file removed on stop, signal handling triggers shutdown, shutdown completes with None components

## 6. CLI Integration

- [x] 6.1 Update `daemon` command in `src/lexibrary/cli.py` to add `--foreground` flag, load config, resolve project root, and call `DaemonService.start()`
- [x] 6.2 Add "not yet implemented" message for invocation without `--foreground`
- [x] 6.3 Update CLI tests to cover the new `--foreground` flag behavior

## 7. Config Alignment

- [x] 7.1 Review `DaemonConfig` schema — add `log_file` field if needed (plan references `daemon.log_file` but current schema only has `debounce_seconds` and `sweep_interval_seconds`)
- [x] 7.2 Ensure `DaemonService` references config field names matching the schema (`sweep_interval_seconds` not `full_sweep_interval_minutes`)

## 8. Verification

- [x] 8.1 Run full test suite: `uv run pytest tests/test_daemon -v`
- [x] 8.2 Run linter and type checker: `uv run ruff check src/ tests/` and `uv run mypy src/`
- [x] 8.3 Manual smoke test: `uv run lexi daemon --foreground` in a test project, modify a file, verify re-indexing fires
