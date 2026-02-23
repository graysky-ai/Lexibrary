# Phase 7: Daemon

**Goal:** Background file watcher with debounced incremental re-indexing and periodic full sweeps.
**Milestone:** `lexi daemon --foreground` watches for changes and updates `.aindex` files automatically.
**Depends on:** Phase 1 (config, ignore, utils), Phase 5 (crawler engine), Phase 6 (CLI daemon command wired up).

---

## 7.1 Architecture Overview

The daemon has three concurrent components:

```
DaemonService
├── watchdog Observer (file system events)
│   └── LexibraryEventHandler
│       └── Debouncer (coalesces rapid events)
│           └── _reindex_directories() callback
├── Periodic Sweep Scheduler
│   └── full_crawl() on timer
└── Signal Handlers (SIGTERM, SIGINT → graceful shutdown)
```

Thread model:
- **Main thread:** blocks on `shutdown_event.wait()`
- **watchdog threads:** Observer runs its own threads for FS events
- **Debouncer timer threads:** `threading.Timer` for debounce delays
- **Sweep timer thread:** `threading.Timer` for periodic full crawl
- **asyncio:** LLM calls run in a temporary event loop (`asyncio.run()`) inside callback threads

---

## 7.2 Event Handler

### File: `src/lexibrary/daemon/watcher.py`

```python
from __future__ import annotations
from pathlib import Path
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from ..ignore.matcher import IgnoreMatcher

class LexibraryEventHandler(FileSystemEventHandler):
    """Watches for file changes and forwards affected directories to the debouncer."""

    def __init__(self, root: Path, matcher: IgnoreMatcher, debouncer):
        self._root = root
        self._matcher = matcher
        self._debouncer = debouncer

    def on_any_event(self, event: FileSystemEvent) -> None:
        # Skip directory events (we care about file changes)
        if event.is_directory:
            return

        path = Path(event.src_path)

        # Skip .aindex files (avoid infinite loop)
        if path.name.startswith(".aindex"):
            return

        # Skip cache and log files
        if path.name in (".lexibrary_cache.json", ".lexibrary.log", ".lexibrary.pid"):
            return

        # Skip ignored files
        if self._matcher.is_ignored(path):
            return

        # Notify the debouncer with the directory containing the changed file
        self._debouncer.notify(path.parent)
```

Key considerations:
- Filter out `.aindex` file changes to prevent recursive re-indexing
- Filter out Lexibrary's own files (cache, log, pid)
- Delegate to debouncer — never do heavy work in the event handler
- `on_any_event` catches creates, modifies, deletes, and moves

---

## 7.3 Debouncer

### File: `src/lexibrary/daemon/debouncer.py`

Coalesces rapid file changes into batched re-index operations.

```python
from __future__ import annotations
import threading
import logging
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

class Debouncer:
    """Coalesces rapid file change events per-directory.

    When a directory is notified, a timer starts (or resets).
    After `delay_seconds` of quiet, the callback fires with all
    accumulated directories.
    """

    def __init__(self, delay_seconds: float, callback: Callable[[set[Path]], None]):
        self._delay = delay_seconds
        self._callback = callback
        self._lock = threading.Lock()
        self._pending: set[Path] = set()
        self._timer: threading.Timer | None = None

    def notify(self, directory: Path) -> None:
        """Register a changed directory. Resets the debounce timer."""
        with self._lock:
            self._pending.add(directory)
            # Cancel existing timer
            if self._timer is not None:
                self._timer.cancel()
            # Start new timer
            self._timer = threading.Timer(self._delay, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        """Called after the debounce period. Triggers re-indexing."""
        with self._lock:
            dirs = self._pending.copy()
            self._pending.clear()
            self._timer = None

        if dirs:
            log.info("Debounce fired: re-indexing %d directories", len(dirs))
            try:
                self._callback(dirs)
            except Exception:
                log.exception("Error during incremental re-index")

    def cancel(self) -> None:
        """Cancel any pending timer."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending.clear()
```

Design notes:
- Single timer for all directories (coalesces across dirs)
- Thread-safe via lock
- Timer is `daemon=True` so it doesn't block process exit
- Errors in callback are logged, not propagated (daemon stays running)

---

## 7.4 Periodic Sweep Scheduler

### File: `src/lexibrary/daemon/scheduler.py`

```python
from __future__ import annotations
import threading
import logging
from typing import Callable

log = logging.getLogger(__name__)

class PeriodicSweep:
    """Triggers a full crawl at regular intervals as a safety net."""

    def __init__(self, interval_minutes: int, callback: Callable[[], None]):
        self._interval = interval_minutes * 60  # convert to seconds
        self._callback = callback
        self._timer: threading.Timer | None = None
        self._running = False

    def start(self) -> None:
        """Start the periodic sweep schedule."""
        self._running = True
        self._schedule_next()

    def stop(self) -> None:
        """Stop the periodic sweep."""
        self._running = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _schedule_next(self) -> None:
        """Schedule the next sweep."""
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._run_sweep)
        self._timer.daemon = True
        self._timer.start()

    def _run_sweep(self) -> None:
        """Execute the sweep and reschedule."""
        log.info("Running periodic full sweep")
        try:
            self._callback()
        except Exception:
            log.exception("Error during periodic sweep")
        self._schedule_next()
```

---

## 7.5 Daemon Service

### File: `src/lexibrary/daemon/service.py`

The main lifecycle manager that ties everything together.

```python
from __future__ import annotations
import asyncio
import logging
import os
import signal
import threading
from pathlib import Path

from watchdog.observers import Observer

from ..config.schema import LexibraryConfig
from ..ignore import create_ignore_matcher
from ..tokenizer import create_tokenizer
from ..llm import create_llm_service
from ..crawler.engine import full_crawl
from ..crawler.change_detector import ChangeDetector
from .watcher import LexibraryEventHandler
from .debouncer import Debouncer
from .scheduler import PeriodicSweep

log = logging.getLogger(__name__)

class DaemonService:
    """Manages the Lexibrary daemon lifecycle."""

    def __init__(self, root: Path, config: LexibraryConfig):
        self._root = root
        self._config = config
        self._observer: Observer | None = None
        self._debouncer: Debouncer | None = None
        self._sweep: PeriodicSweep | None = None
        self._shutdown = threading.Event()
        self._pid_file = root / ".lexibrary.pid"

    def start(self, foreground: bool = False) -> None:
        """Start the daemon."""
        from ..utils.logging import setup_logging
        setup_logging(verbose=True, log_file=str(self._root / self._config.daemon.log_file))

        log.info("Starting Lexibrary daemon for %s", self._root)
        self._write_pid_file()
        self._setup_signal_handlers()

        # Build shared components
        matcher = create_ignore_matcher(self._config, self._root)

        # Start debouncer → watcher
        self._debouncer = Debouncer(
            delay_seconds=self._config.daemon.debounce_seconds,
            callback=lambda dirs: self._incremental_reindex(dirs),
        )

        handler = LexibraryEventHandler(self._root, matcher, self._debouncer)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._root), recursive=True)
        self._observer.start()
        log.info("File watcher started (debounce: %.1fs)", self._config.daemon.debounce_seconds)

        # Start periodic sweep
        self._sweep = PeriodicSweep(
            interval_minutes=self._config.daemon.full_sweep_interval_minutes,
            callback=self._full_sweep,
        )
        self._sweep.start()
        log.info("Periodic sweep scheduled every %d minutes", self._config.daemon.full_sweep_interval_minutes)

        log.info("Daemon ready. Watching for changes...")
        print(f"Lexibrary daemon running (PID {os.getpid()}). Press Ctrl+C to stop.")

        # Block until shutdown signal
        try:
            self._shutdown.wait()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        """Graceful shutdown."""
        log.info("Shutting down daemon...")
        self._shutdown.set()

        if self._debouncer:
            self._debouncer.cancel()
        if self._sweep:
            self._sweep.stop()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)

        self._remove_pid_file()
        log.info("Daemon stopped.")

    def _setup_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: self._shutdown.set())
        signal.signal(signal.SIGINT, lambda *_: self._shutdown.set())

    def _write_pid_file(self) -> None:
        self._pid_file.write_text(str(os.getpid()))

    def _remove_pid_file(self) -> None:
        try:
            self._pid_file.unlink(missing_ok=True)
        except OSError:
            pass

    def _incremental_reindex(self, directories: set[Path]) -> None:
        """Re-index affected directories and their ancestors."""
        log.info("Incremental re-index for %d directories", len(directories))

        # Expand to include parent directories up to root
        all_dirs: set[Path] = set()
        for d in directories:
            current = d
            while current != self._root.parent:
                all_dirs.add(current)
                current = current.parent

        # Sort deepest first
        sorted_dirs = sorted(all_dirs, key=lambda p: len(p.parts), reverse=True)

        # Run crawl for each directory
        # (Reuses the same engine logic but scoped to specific directories)
        matcher = create_ignore_matcher(self._config, self._root)
        tokenizer = create_tokenizer(self._config.tokenizer)
        llm_service = create_llm_service(self._config.llm)
        cache_path = self._root / ".lexibrary_cache.json"
        change_detector = ChangeDetector(cache_path)
        change_detector.load()

        asyncio.run(full_crawl(
            root=self._root,
            config=self._config,
            llm_service=llm_service,
            tokenizer=tokenizer,
            matcher=matcher,
            change_detector=change_detector,
        ))

        log.info("Incremental re-index complete")

    def _full_sweep(self) -> None:
        """Run a complete crawl as a safety net."""
        log.info("Running full sweep")
        matcher = create_ignore_matcher(self._config, self._root)
        tokenizer = create_tokenizer(self._config.tokenizer)
        llm_service = create_llm_service(self._config.llm)
        cache_path = self._root / ".lexibrary_cache.json"
        change_detector = ChangeDetector(cache_path)
        change_detector.load()

        stats = asyncio.run(full_crawl(
            root=self._root,
            config=self._config,
            llm_service=llm_service,
            tokenizer=tokenizer,
            matcher=matcher,
            change_detector=change_detector,
        ))
        log.info(
            "Full sweep complete: %d dirs, %d files summarized, %d cached",
            stats.directories_indexed, stats.files_summarized, stats.files_cached,
        )
```

---

## 7.6 `__init__.py`

### File: `src/lexibrary/daemon/__init__.py`

```python
from .service import DaemonService

__all__ = ["DaemonService"]
```

---

## 7.7 Tests

### File: `tests/test_daemon/test_debouncer.py`

| Test | What it verifies |
|------|-----------------|
| `test_debounce_fires_after_delay` | Callback fires after quiet period |
| `test_debounce_resets_on_new_event` | Rapid events reset the timer, callback fires once |
| `test_debounce_accumulates_directories` | Multiple different dirs collected in single callback |
| `test_debounce_cancel` | Cancel prevents pending callback from firing |

### File: `tests/test_daemon/test_scheduler.py`

| Test | What it verifies |
|------|-----------------|
| `test_sweep_fires_on_schedule` | Callback fires after interval (use short test interval) |
| `test_sweep_stop` | Stop prevents further callbacks |
| `test_sweep_reschedules` | After first callback, next one is scheduled |

### File: `tests/test_daemon/test_watcher.py`

| Test | What it verifies |
|------|-----------------|
| `test_handler_ignores_directories` | Directory events are filtered |
| `test_handler_ignores_iandex_files` | `.aindex` changes don't trigger |
| `test_handler_ignores_cache_files` | Cache/log/pid files don't trigger |
| `test_handler_notifies_debouncer` | Valid file change calls `debouncer.notify()` |
| `test_handler_ignores_gitignored_files` | Ignored files don't trigger |

### File: `tests/test_daemon/test_service.py`

| Test | What it verifies |
|------|-----------------|
| `test_pid_file_created_on_start` | PID file written at startup |
| `test_pid_file_removed_on_stop` | PID file removed at shutdown |
| `test_signal_handling` | SIGTERM triggers graceful shutdown |

Note: Daemon tests use short intervals (0.1s debounce, 1s sweep) and `tmp_path` fixtures. Mock the LLM service to avoid real API calls.

---

## Acceptance Criteria

- [ ] `lexi daemon --foreground` starts and prints "running" message
- [ ] Modifying a file triggers re-indexing after debounce period
- [ ] Rapid changes are coalesced (not indexed per-keystroke)
- [ ] Parent directories are re-indexed when child `.aindex` changes
- [ ] Periodic sweep runs at the configured interval
- [ ] Ctrl+C (SIGINT) triggers graceful shutdown
- [ ] SIGTERM triggers graceful shutdown
- [ ] PID file is created on start and removed on stop
- [ ] `.aindex` changes don't cause recursive re-indexing
- [ ] Errors in re-indexing are logged but don't crash the daemon
- [ ] All tests pass: `uv run pytest tests/test_daemon -v`
