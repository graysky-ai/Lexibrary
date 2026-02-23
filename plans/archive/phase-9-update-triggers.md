# Phase 9 -- Update Triggers & CI Integration

**Reference:** `plans/v2-master-plan.md` (Phase 9 section), `lexibrary-overview.md` (sections 7, 9)
**Depends on:** Phase 4 (Archivist pipeline -- `update_file()`, `update_project()`)
**Parallelisable with:** Phase 8 (CLI Split, Init Wizard, Agent Rules), Phase 10 (Reverse Dependency Index)
**Consumed by:** Phase 10 (reverse index uses `update_project()`), Phase 11 (query index)

---

## Goal

Deliver automated library maintenance via git hooks (primary trigger), periodic sweep (safety net), and CI integration. Rewrite the broken `DaemonService` to use the archivist pipeline. Add safety mechanisms (atomic writes, conflict marker detection, design hash re-check) that protect all trigger modes. Deprecate the watchdog daemon (off by default).

---

## Current State Assessment

### What works

| Component | File | Status |
|-----------|------|--------|
| `Debouncer` | `daemon/debouncer.py` | Clean, correct, reusable |
| `PeriodicSweep` | `daemon/scheduler.py` | Clean, correct, reusable |
| `LexibrarianEventHandler` | `daemon/watcher.py` | Clean, correct, reusable |
| `update_file()` | `archivist/pipeline.py` | Fully functional -- the correct update engine |
| `update_project()` | `archivist/pipeline.py` | Fully functional -- full project sweep |
| `lexictl update [path]` | `cli/lexictl_app.py` | Working CLI command |

### What is broken

| Component | Problem |
|-----------|---------|
| `DaemonService` | Wired to retired `full_crawl()` from `crawler/engine.py`; references `config.output.log_filename`, `config.output.cache_filename`, `config.tokenizer` -- none of which exist on `LexibraryConfig`; mypy `ignore_errors = true` |
| `DaemonConfig` | Missing fields: `sweep_skip_if_unchanged`, `git_suppression_seconds`, `watchdog_enabled`, `log_level`; wrong default for `sweep_interval_seconds` (300 vs 3600) |
| Design file writes | Not atomic -- `design_path.write_text()` directly; agent edits during LLM generation can be overwritten |
| No `--changed-only` flag | Git hook integration requires processing only named files |
| No conflict marker detection | Files with merge conflicts can be sent to the LLM |
| No `lexictl setup --hooks` | Git hook installation not implemented |
| No `lexictl sweep` command | One-shot and watch-mode sweep not available |
| `lexictl daemon` | Stub -- prints "Not yet implemented" |

---

## Decisions Referenced

| # | Decision | Resolution |
|---|----------|------------|
| D-025 | Concurrency model | Sequential for MVP. Async architecture from the start. |
| D-059 | Foreground-only daemon | No background daemonization. User's terminal handles lifecycle. |
| D-060 | Atomic writes | All `.lexibrary/` writes use write-to-temp-then-`os.replace()`. |
| D-061 | Design hash re-check | Re-check `design_hash` after LLM generation, before write. Discard if agent edited during LLM call. |
| D-062 | Git suppression window | Watchdog watches `.git/HEAD`; suppresses events after branch switch (5s default). |
| D-063 | Conflict marker detection | Skip files with `<<<<<<<` at start of line. Log as warning. |
| D-064 | `.aindex` write lock | Per-directory lock for concurrent `.aindex` writes. No-op under sequential MVP. |
| D-065 | Watchdog deprecated | Off by default (`daemon.watchdog_enabled: false`). Retained for human-heavy teams. |
| D-066 | Sweep skip-if-unchanged | Scan `scope_root` mtimes before sweep; skip if nothing newer than last sweep. |
| D-067 | Git post-commit hook | `lexictl setup --hooks` installs post-commit hook running `lexictl update --changed-only` in background. |

---

## Sub-Phases

| Sub-Phase | Name | Depends On | Can Parallel With | Task Groups |
|-----------|------|------------|-------------------|-------------|
| **9a** | Config & Logging | Phase 1 (config schema) | 9b | Config schema update, `RotatingFileHandler` setup |
| **9b** | Safety Mechanisms | Phase 4 (pipeline) | 9a | Atomic writes, conflict detection, design hash re-check |
| **9c** | Pipeline Extensions | 9b (safety mechanisms) | -- | `--changed-only` flag, `update_files()` batch function |
| **9d** | DaemonService Rewrite | 9a, 9b, 9c | -- | Rewire to archivist pipeline, sweep skip-if-unchanged |
| **9e** | Git Hook Installation | 9c (--changed-only) | 9d | `lexictl setup --hooks`, hook script generation |
| **9f** | CLI Commands | 9d, 9e | -- | `lexictl sweep`, `lexictl daemon`, `lexictl update --changed-only` |

**Critical path:** 9a + 9b (parallel) → 9c → 9d → 9f
**Independent:** 9e can start once 9c is done

---

## 9a -- Config Schema & Logging

### Config Schema Changes

Update `DaemonConfig` in `src/lexibrarian/config/schema.py`:

```python
class DaemonConfig(BaseModel):
    """Daemon and sweep configuration."""

    model_config = ConfigDict(extra="ignore")

    debounce_seconds: float = 2.0
    sweep_interval_seconds: int = 3600
    sweep_skip_if_unchanged: bool = True
    git_suppression_seconds: int = 5
    watchdog_enabled: bool = False
    log_level: str = "info"
```

Field changes from current `DaemonConfig`:
- `sweep_interval_seconds`: default 300 → 3600 (60 minutes)
- `enabled: bool = True` → **removed** (replaced by `watchdog_enabled`)
- `sweep_skip_if_unchanged: bool = True` → **new**
- `git_suppression_seconds: int = 5` → **new**
- `watchdog_enabled: bool = False` → **new** (replaces `enabled`, default flipped to `False`)
- `log_level: str = "info"` → **new**

**Migration note:** The `enabled` field is removed. Any existing config files with `daemon.enabled: true` will be silently ignored (`extra="ignore"`). The `watchdog_enabled` field replaces it with an explicit name and opposite default. This is acceptable pre-1.0.

### Config Defaults Template

Update `src/lexibrarian/config/defaults.py` to reflect:

```yaml
daemon:
  debounce_seconds: 2.0
  sweep_interval_seconds: 3600
  sweep_skip_if_unchanged: true
  git_suppression_seconds: 5
  watchdog_enabled: false
  log_level: info
```

### Logging Setup

Create `src/lexibrarian/daemon/logging.py`:

```python
"""Daemon-specific logging with RotatingFileHandler."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FILENAME = ".lexibrarian.log"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3
_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"


def setup_daemon_logging(
    project_root: Path,
    log_level: str = "info",
) -> None:
    """Configure logging for daemon/sweep processes.

    Writes to .lexibrarian.log in project root with rotation.
    Does NOT configure console logging -- callers add their own
    console handler if needed.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    log_path = project_root / _LOG_FILENAME

    handler = RotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    logger = logging.getLogger("lexibrarian")
    logger.setLevel(level)
    logger.addHandler(handler)
```

The `.lexibrarian.log` file must be gitignored. `lexictl init` already creates `.gitignore` entries for `.lexibrary/` internals; verify that `.lexibrarian.log` is included. If not, add it to the scaffolder's gitignore additions.

---

## 9b -- Safety Mechanisms

### Atomic Writes (D-060)

Create `src/lexibrarian/utils/atomic.py`:

```python
"""Atomic file write utility using temp-file + os.replace()."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(target: Path, content: str, encoding: str = "utf-8") -> None:
    """Write content to target atomically.

    Creates a temp file in the same directory as target, writes content,
    then replaces target via os.replace(). This is atomic on POSIX and
    near-atomic on Windows.

    The temp file is in the same directory to ensure same-filesystem
    rename (required by os.replace()).
    """
    target_dir = target.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp_path, target)
    except BaseException:
        # Clean up temp file on any failure
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
```

**Adoption:** All writes to `.lexibrary/` from the archivist pipeline should use `atomic_write()` instead of `Path.write_text()`. The following call sites in `archivist/pipeline.py` need updating:

| Line | Current | New |
|------|---------|-----|
| `pipeline.py` line 114 | `design_path.write_text(serialized, ...)` | `atomic_write(design_path, serialized)` |
| `pipeline.py` line 146 | `design_path.write_text(new_text, ...)` | `atomic_write(design_path, new_text)` |
| `pipeline.py` line 185 | `aindex_file_path.write_text(serialized, ...)` | `atomic_write(aindex_file_path, serialized)` |
| `pipeline.py` line 320 | `design_path.write_text(serialized, ...)` | `atomic_write(design_path, serialized)` |

### Conflict Marker Detection (D-063)

Create `src/lexibrarian/utils/conflict.py`:

```python
"""Git merge conflict marker detection."""

from __future__ import annotations

from pathlib import Path


def has_conflict_markers(source_path: Path) -> bool:
    """Check whether a source file contains git conflict markers.

    Looks for lines starting with '<<<<<<< ' (7 angle brackets + space).
    Reads in text mode; returns False on read errors.
    """
    try:
        with source_path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("<<<<<<<"):
                    return True
    except OSError:
        return False
    return False
```

**Integration point:** Called in `update_file()` before LLM generation (after change detection, before reading source content). If detected, log a warning and return `FileResult(change=change, failed=True)` with a clear log message.

### Design Hash Re-check (D-061)

Add a re-check step to `update_file()` in the LLM generation path. After `archivist.generate_design_file()` returns and before writing, re-read the design file's `design_hash` and compare against the hash recorded before the LLM call started. If they differ, an agent edited the file during the LLM call -- discard the LLM output.

```python
# In update_file(), after LLM generation succeeds, before writing:

# D-061: Re-check design_hash before write -- agent may have edited during LLM call
if design_path.exists():
    current_meta = parse_design_file_metadata(design_path)
    if current_meta is not None and pre_llm_design_hash is not None:
        if current_meta.design_hash != pre_llm_design_hash:
            logger.info(
                "Design file for %s was edited during LLM generation "
                "(design_hash changed). Discarding LLM output.",
                rel_path,
            )
            return FileResult(change=ChangeLevel.AGENT_UPDATED, aindex_refreshed=False)
```

The `pre_llm_design_hash` is captured from `parse_design_file_metadata()` before the LLM call starts.

### `.aindex` Write Serialisation (D-064)

Create `src/lexibrarian/utils/locks.py`:

```python
"""Per-directory write locks for .aindex serialisation."""

from __future__ import annotations

import threading
from pathlib import Path


class DirectoryLockManager:
    """Provides per-directory locks for serialising .aindex writes.

    Under sequential MVP processing (D-025), these locks are effectively
    no-ops. They exist so the concurrency upgrade is safe.
    """

    def __init__(self) -> None:
        self._locks: dict[Path, threading.Lock] = {}
        self._manager_lock = threading.Lock()

    def get_lock(self, directory: Path) -> threading.Lock:
        """Return the lock for a specific directory, creating if needed."""
        with self._manager_lock:
            if directory not in self._locks:
                self._locks[directory] = threading.Lock()
            return self._locks[directory]
```

**Integration:** Pass `DirectoryLockManager` to `_refresh_parent_aindex()`. Acquire the directory lock before reading and writing the `.aindex` file. Under the sequential MVP, this is a no-op but ensures correctness when async processing is added later.

---

## 9c -- Pipeline Extensions

### `--changed-only` Flag

Add a new function to `archivist/pipeline.py` for processing a specific list of files:

```python
async def update_files(
    file_paths: list[Path],
    project_root: Path,
    config: LexibraryConfig,
    archivist: ArchivistService,
    progress_callback: ProgressCallback | None = None,
) -> UpdateStats:
    """Update design files for a specific list of source files.

    Used by git hooks and CI to process only the files that changed
    in a commit, rather than scanning the entire project.

    Does NOT regenerate START_HERE.md -- that is a full-project concern.
    """
    stats = UpdateStats()
    ignore_matcher = create_ignore_matcher(config, project_root)
    binary_exts = set(config.crawl.binary_extensions)

    # Load available concept names
    concepts_dir = project_root / LEXIBRARY_DIR / "concepts"
    concept_index = ConceptIndex.load(concepts_dir)
    available_concepts = concept_index.names() or None

    for source_path in file_paths:
        source_path = source_path.resolve()

        # Skip non-existent files (deleted in commit)
        if not source_path.exists():
            continue

        # Skip binary files
        if _is_binary(source_path, binary_exts):
            continue

        # Skip ignored files
        if ignore_matcher.is_ignored(source_path):
            continue

        # Skip .lexibrary contents
        try:
            source_path.relative_to(project_root / LEXIBRARY_DIR)
            continue
        except ValueError:
            pass

        stats.files_scanned += 1

        try:
            file_result = await update_file(
                source_path,
                project_root,
                config,
                archivist,
                available_concepts=available_concepts,
            )
        except Exception:
            logger.exception("Unexpected error processing %s", source_path)
            stats.files_failed += 1
            if progress_callback is not None:
                progress_callback(source_path, ChangeLevel.UNCHANGED)
            continue

        # Accumulate stats (same logic as update_project)
        change = file_result.change
        if file_result.failed:
            stats.files_failed += 1
        elif change == ChangeLevel.UNCHANGED:
            stats.files_unchanged += 1
        elif change == ChangeLevel.AGENT_UPDATED:
            stats.files_agent_updated += 1
        elif change == ChangeLevel.NEW_FILE:
            stats.files_created += 1
        elif change in (
            ChangeLevel.CONTENT_ONLY,
            ChangeLevel.CONTENT_CHANGED,
            ChangeLevel.INTERFACE_CHANGED,
        ):
            stats.files_updated += 1

        if file_result.aindex_refreshed:
            stats.aindex_refreshed += 1
        if file_result.token_budget_exceeded:
            stats.token_budget_warnings += 1

        if progress_callback is not None:
            progress_callback(source_path, change)

    return stats
```

### CLI Integration

Update `lexictl update` in `cli/lexictl_app.py` to accept `--changed-only`:

```python
@lexictl_app.command()
def update(
    path: Annotated[
        Path | None,
        typer.Argument(help="File or directory to update. Omit to update entire project."),
    ] = None,
    *,
    changed_only: Annotated[
        list[Path] | None,
        typer.Option(
            "--changed-only",
            help="Update only the specified files (for git hooks/CI).",
        ),
    ] = None,
) -> None:
```

When `--changed-only` is provided, call `update_files()` instead of `update_project()`. The `path` argument and `--changed-only` are mutually exclusive -- error if both provided.

---

## 9d -- DaemonService Rewrite

### Complete Rewrite of `daemon/service.py`

The current `DaemonService` is non-functional. Rewrite it to:

1. Use `archivist/pipeline.py` (`update_project()`, `update_files()`) instead of `full_crawl()`
2. Use `setup_daemon_logging()` instead of broken `config.output.log_filename`
3. Support two modes: **sweep** (primary) and **watchdog** (deprecated)
4. Implement skip-if-unchanged for sweeps (D-066)
5. Add git suppression window for watchdog mode (D-062)

```python
"""Daemon service: sweep mode (primary) and watchdog mode (deprecated)."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import threading
from pathlib import Path
from types import FrameType

from rich.console import Console

from lexibrarian.config import find_config_file, load_config
from lexibrarian.config.schema import LexibraryConfig
from lexibrarian.daemon.logging import setup_daemon_logging
from lexibrarian.daemon.scheduler import PeriodicSweep
from lexibrarian.utils.paths import LEXIBRARY_DIR

logger = logging.getLogger(__name__)
console = Console()

_PID_FILENAME = ".lexibrarian.pid"


class DaemonService:
    """Orchestrates sweep mode and optional watchdog mode.

    Primary mode (sweep): periodic full-project update with skip-if-unchanged.
    Deprecated mode (watchdog): real-time file watching with debounce.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._shutdown_event = threading.Event()
        self._sweep: PeriodicSweep | None = None
        self._observer: object | None = None  # watchdog.Observer when enabled
        self._last_sweep_time: float = 0.0

    def run_once(self) -> None:
        """Run a single sweep (process pending changes, then exit)."""
        config = self._load_config()
        setup_daemon_logging(self._root, config.daemon.log_level)

        if config.daemon.sweep_skip_if_unchanged and not self._has_changes(config):
            console.print("[dim]No changes detected -- sweep skipped.[/dim]")
            logger.info("Sweep skipped -- no changes detected")
            return

        self._run_sweep(config)

    def run_watch(self) -> None:
        """Run periodic sweeps in foreground until interrupted."""
        config = self._load_config()
        setup_daemon_logging(self._root, config.daemon.log_level)

        self._sweep = PeriodicSweep(
            interval=float(config.daemon.sweep_interval_seconds),
            callback=lambda: self._sweep_with_skip(config),
        )

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self._sweep.start()
        console.print(
            f"[green]Sweep mode running[/green] "
            f"(interval: {config.daemon.sweep_interval_seconds}s) "
            f"watching [cyan]{self._root}[/cyan]\n"
            "Press Ctrl+C to stop."
        )
        logger.info(
            "Sweep mode started (interval=%ds) watching %s",
            config.daemon.sweep_interval_seconds,
            self._root,
        )

        self._shutdown_event.wait()
        self.stop()

    def run_watchdog(self) -> None:
        """Run deprecated watchdog mode (real-time file watching)."""
        from watchdog.observers import Observer  # noqa: PLC0415

        from lexibrarian.daemon.debouncer import Debouncer  # noqa: PLC0415
        from lexibrarian.daemon.watcher import LexibrarianEventHandler  # noqa: PLC0415
        from lexibrarian.ignore import create_ignore_matcher  # noqa: PLC0415

        config = self._load_config()
        setup_daemon_logging(self._root, config.daemon.log_level)

        if not config.daemon.watchdog_enabled:
            console.print(
                "[yellow]Watchdog mode is disabled.[/yellow]\n"
                "Set [cyan]daemon.watchdog_enabled: true[/cyan] in config, "
                "or use [cyan]lexictl sweep --watch[/cyan] instead."
            )
            return

        console.print(
            "[yellow]Warning:[/yellow] Watchdog mode is deprecated. "
            "Git hooks + periodic sweep are recommended instead."
        )

        ignore_matcher = create_ignore_matcher(config, self._root)

        debouncer = Debouncer(
            delay=config.daemon.debounce_seconds,
            callback=lambda dirs: self._debounce_callback(config, dirs),
        )

        handler = LexibrarianEventHandler(
            debouncer=debouncer,
            ignore_matcher=ignore_matcher,
        )

        self._observer = Observer()
        self._observer.schedule(handler, str(self._root), recursive=True)

        # Also start periodic sweep as safety net
        self._sweep = PeriodicSweep(
            interval=float(config.daemon.sweep_interval_seconds),
            callback=lambda: self._sweep_with_skip(config),
        )

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self._write_pid_file()
        self._observer.start()
        self._sweep.start()

        pid = os.getpid()
        console.print(
            f"[green]Watchdog running[/green] (PID {pid}) "
            f"watching [cyan]{self._root}[/cyan]\n"
            "Press Ctrl+C to stop."
        )
        logger.info("Watchdog started (PID %d) watching %s", pid, self._root)

        self._shutdown_event.wait()
        self.stop()

    def stop(self) -> None:
        """Gracefully stop all daemon components."""
        logger.info("Daemon shutting down...")

        if self._sweep is not None:
            self._sweep.stop()

        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)

        self._remove_pid_file()
        console.print("[yellow]Stopped.[/yellow]")
        logger.info("Daemon stopped.")

    # -- Internal helpers --

    def _load_config(self) -> LexibraryConfig:
        """Load project config."""
        from lexibrarian.config.loader import load_config  # noqa: PLC0415

        return load_config(self._root)

    def _has_changes(self, config: LexibraryConfig) -> bool:
        """Check if any file in scope_root has mtime newer than last sweep.

        Uses os.scandir() stat walk -- no hashing, no file reads (D-066).
        """
        scope_abs = (self._root / config.scope_root).resolve()
        lexibrary_abs = (self._root / LEXIBRARY_DIR).resolve()

        if self._last_sweep_time == 0.0:
            # First sweep -- always run
            return True

        try:
            for entry in os.scandir(scope_abs):
                if self._scan_for_changes(entry, lexibrary_abs):
                    return True
        except OSError:
            # If we can't scan, assume changes exist
            return True

        return False

    def _scan_for_changes(self, entry: os.DirEntry[str], skip_dir: Path) -> bool:
        """Recursively check if any file has mtime newer than last sweep."""
        try:
            if entry.is_dir(follow_symlinks=False):
                if Path(entry.path).resolve() == skip_dir:
                    return False
                for sub_entry in os.scandir(entry.path):
                    if self._scan_for_changes(sub_entry, skip_dir):
                        return True
            elif entry.is_file(follow_symlinks=False):
                stat = entry.stat(follow_symlinks=False)
                if stat.st_mtime > self._last_sweep_time:
                    return True
        except OSError:
            pass
        return False

    def _sweep_with_skip(self, config: LexibraryConfig) -> None:
        """Run sweep with skip-if-unchanged check."""
        if config.daemon.sweep_skip_if_unchanged and not self._has_changes(config):
            logger.debug("Sweep skipped -- no changes detected")
            return
        self._run_sweep(config)

    def _run_sweep(self, config: LexibraryConfig) -> None:
        """Execute a full project update sweep."""
        import time  # noqa: PLC0415

        from lexibrarian.archivist.pipeline import update_project  # noqa: PLC0415
        from lexibrarian.archivist.service import ArchivistService  # noqa: PLC0415
        from lexibrarian.llm.rate_limiter import RateLimiter  # noqa: PLC0415

        logger.info("Sweep started")
        start = time.monotonic()

        rate_limiter = RateLimiter()
        archivist = ArchivistService(rate_limiter=rate_limiter, config=config.llm)

        try:
            stats = asyncio.run(update_project(self._root, config, archivist))
            elapsed = time.monotonic() - start
            logger.info(
                "Sweep complete in %.1fs: %d scanned, %d updated, "
                "%d created, %d failed",
                elapsed,
                stats.files_scanned,
                stats.files_updated,
                stats.files_created,
                stats.files_failed,
            )
            console.print(
                f"[green]Sweep complete[/green] ({elapsed:.1f}s): "
                f"{stats.files_scanned} scanned, "
                f"{stats.files_updated} updated, "
                f"{stats.files_created} created"
            )
        except Exception:
            logger.exception("Sweep failed")

        self._last_sweep_time = time.time()

    def _debounce_callback(self, config: LexibraryConfig, dirs: set[Path]) -> None:
        """Watchdog debounce callback: update files in changed directories."""
        from lexibrarian.archivist.pipeline import update_project  # noqa: PLC0415
        from lexibrarian.archivist.service import ArchivistService  # noqa: PLC0415
        from lexibrarian.llm.rate_limiter import RateLimiter  # noqa: PLC0415

        logger.info("Debounce callback triggered for %d directories", len(dirs))

        rate_limiter = RateLimiter()
        archivist = ArchivistService(rate_limiter=rate_limiter, config=config.llm)

        try:
            # For watchdog mode, run full update -- update_project handles
            # change detection internally and skips unchanged files
            stats = asyncio.run(update_project(self._root, config, archivist))
            logger.info(
                "Debounce update: %d scanned, %d updated, %d created",
                stats.files_scanned,
                stats.files_updated,
                stats.files_created,
            )
        except Exception:
            logger.exception("Debounce update failed")

    def _signal_handler(self, signum: int, frame: FrameType | None) -> None:
        """Handle SIGTERM/SIGINT by triggering shutdown."""
        logger.info("Received signal %d, shutting down...", signum)
        self._shutdown_event.set()

    def _write_pid_file(self) -> None:
        """Write current PID to PID file."""
        pid_path = self._root / _PID_FILENAME
        pid_path.write_text(str(os.getpid()), encoding="utf-8")

    def _remove_pid_file(self) -> None:
        """Remove PID file, tolerating if already gone."""
        pid_path = self._root / _PID_FILENAME
        pid_path.unlink(missing_ok=True)
```

### Key Design Decisions in the Rewrite

1. **Three entry points:** `run_once()` (single sweep), `run_watch()` (periodic), `run_watchdog()` (deprecated real-time). All share the same update engine.

2. **Skip-if-unchanged uses `os.scandir()` stat walk** (D-066) -- no hashing, no file reads. Recursive scan with early return on first changed file.

3. **Watchdog imports are lazy** -- `watchdog` library is only imported when `run_watchdog()` is called. The sweep modes work without it installed.

4. **Config is reloaded per-sweep** in `run_watch()` -- this allows config changes to take effect without restart.

5. **`asyncio.run()` bridges threading and async** -- the scheduler/debouncer callbacks run in threads; `asyncio.run()` creates a fresh event loop for each update invocation. This matches the pattern already used in `lexictl update`.

---

## 9e -- Git Hook Installation

### `lexictl setup --hooks`

Add `--hooks` flag to the existing `setup` command in `cli/lexictl_app.py`:

```python
@lexictl_app.command()
def setup(
    *,
    update_flag: Annotated[
        bool,
        typer.Option("--update", help="Update existing agent rules."),
    ] = False,
    hooks_flag: Annotated[
        bool,
        typer.Option("--hooks", help="Install git post-commit hook."),
    ] = False,
) -> None:
```

### Hook Script

Create `src/lexibrarian/hooks/post_commit.py`:

```python
"""Git post-commit hook generation and installation."""

from __future__ import annotations

import os
import stat
from pathlib import Path

_HOOK_MARKER = "# lexibrarian:post-commit"

_HOOK_SCRIPT = """\
#!/bin/sh
# lexibrarian:post-commit
# Auto-generated by: lexictl setup --hooks
# Updates design files for committed changes in the background.

changed_files=$(git diff-tree --no-commit-id --name-only -r HEAD)
if [ -n "$changed_files" ]; then
    lexictl update --changed-only $changed_files >> .lexibrarian.log 2>&1 &
fi
"""


def install_post_commit_hook(project_root: Path) -> str:
    """Install or append Lexibrarian post-commit hook.

    Returns a status message describing what was done.

    Handles three cases:
    1. No .git/hooks/post-commit exists -- create it
    2. Existing hook without Lexibrarian marker -- append
    3. Existing hook with Lexibrarian marker -- already installed
    """
    git_dir = project_root / ".git"
    if not git_dir.is_dir():
        return "No .git directory found -- is this a git repository?"

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    hook_path = hooks_dir / "post-commit"

    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8")

        if _HOOK_MARKER in existing:
            return "Lexibrarian post-commit hook already installed."

        # Append to existing hook
        hook_path.write_text(
            existing.rstrip("\n") + "\n\n" + _HOOK_SCRIPT,
            encoding="utf-8",
        )
        _make_executable(hook_path)
        return "Appended Lexibrarian hook to existing post-commit hook."

    # Create new hook
    hook_path.write_text(_HOOK_SCRIPT, encoding="utf-8")
    _make_executable(hook_path)
    return "Created post-commit hook."


def _make_executable(path: Path) -> None:
    """Add executable permission to a file."""
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
```

### What the hook does

1. `git diff-tree --no-commit-id --name-only -r HEAD` -- lists files changed in the most recent commit
2. Passes the list to `lexictl update --changed-only`
3. Runs in background (`&`) so the user's terminal is not blocked
4. Output goes to `.lexibrarian.log`

### Uninstall

No `--remove-hooks` command in MVP. Users can manually delete the hook or remove the `# lexibrarian:post-commit` section. Document this in help text.

---

## 9f -- CLI Commands

### `lexictl sweep`

```python
@lexictl_app.command()
def sweep(
    *,
    watch: Annotated[
        bool,
        typer.Option("--watch", help="Run periodic sweeps in foreground."),
    ] = False,
) -> None:
    """Run a library update sweep."""
    from lexibrarian.daemon.service import DaemonService  # noqa: PLC0415

    project_root = require_project_root()
    service = DaemonService(project_root)

    if watch:
        service.run_watch()
    else:
        service.run_once()
```

### `lexictl daemon`

Replace the stub with a working (but deprecated) command:

```python
@lexictl_app.command()
def daemon(
    action: Annotated[
        str,
        typer.Argument(help="Action: start, stop, or status."),
    ] = "start",
) -> None:
    """[Deprecated] Real-time file watcher. Use 'lexictl sweep --watch' instead."""
    from lexibrarian.daemon.service import DaemonService  # noqa: PLC0415

    project_root = require_project_root()
    service = DaemonService(project_root)

    if action == "start":
        service.run_watchdog()
    elif action == "stop":
        _stop_daemon(project_root)
    elif action == "status":
        _daemon_status(project_root)
    else:
        console.print(f"[red]Unknown action:[/red] {action}")
        console.print("Usage: lexictl daemon [start|stop|status]")
        raise typer.Exit(1)
```

The `_stop_daemon()` and `_daemon_status()` helpers read the PID file and send signals:

```python
def _stop_daemon(project_root: Path) -> None:
    """Stop a running daemon by PID file."""
    pid_path = project_root / ".lexibrarian.pid"
    if not pid_path.exists():
        console.print("[yellow]No daemon running (no PID file found).[/yellow]")
        return

    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Sent SIGTERM to daemon (PID {pid}).[/green]")
    except (ValueError, ProcessLookupError, PermissionError) as e:
        console.print(f"[yellow]Could not stop daemon:[/yellow] {e}")
        pid_path.unlink(missing_ok=True)


def _daemon_status(project_root: Path) -> None:
    """Check if a daemon is running via PID file."""
    pid_path = project_root / ".lexibrarian.pid"
    if not pid_path.exists():
        console.print("No daemon running.")
        return

    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 0)  # signal 0 checks if process exists
        console.print(f"[green]Daemon running[/green] (PID {pid})")
    except (ValueError, ProcessLookupError):
        console.print("[yellow]Stale PID file -- daemon not running.[/yellow]")
        pid_path.unlink(missing_ok=True)
    except PermissionError:
        console.print(f"Daemon may be running (PID {pid}) -- permission denied for status check.")
```

### `lexictl update --changed-only`

As specified in 9c. The `--changed-only` option accepts a list of file paths relative to the project root.

---

## Files to Create

| File | Purpose |
|------|---------|
| `src/lexibrarian/daemon/logging.py` | `RotatingFileHandler` setup for `.lexibrarian.log` |
| `src/lexibrarian/utils/atomic.py` | `atomic_write()` -- temp file + `os.replace()` |
| `src/lexibrarian/utils/conflict.py` | `has_conflict_markers()` -- merge conflict detection |
| `src/lexibrarian/utils/locks.py` | `DirectoryLockManager` -- per-directory `.aindex` write locks |
| `src/lexibrarian/hooks/__init__.py` | Hooks package init |
| `src/lexibrarian/hooks/post_commit.py` | Git post-commit hook generation and installation |
| `tests/test_daemon/test_logging.py` | Tests for daemon logging setup |
| `tests/test_daemon/test_service_rewrite.py` | Tests for rewritten `DaemonService` |
| `tests/test_hooks/__init__.py` | Hooks test package init |
| `tests/test_hooks/test_post_commit.py` | Tests for hook installation |
| `tests/test_utils/test_atomic.py` | Tests for atomic write |
| `tests/test_utils/test_conflict.py` | Tests for conflict marker detection |
| `tests/test_utils/test_locks.py` | Tests for directory lock manager |

## Files to Modify

| File | Change |
|------|--------|
| `src/lexibrarian/config/schema.py` | Update `DaemonConfig` fields |
| `src/lexibrarian/config/defaults.py` | Update default config template |
| `src/lexibrarian/archivist/pipeline.py` | Add `update_files()`, adopt `atomic_write()`, add conflict marker check, add D-061 re-check |
| `src/lexibrarian/daemon/service.py` | Complete rewrite |
| `src/lexibrarian/daemon/__init__.py` | Update exports if needed |
| `src/lexibrarian/cli/lexictl_app.py` | Add `--changed-only` to `update`, add `--hooks` to `setup`, replace `daemon` stub, add `sweep` command |
| `src/lexibrarian/utils/logging.py` | May need minor updates to coexist with daemon-specific logging |
| `src/lexibrarian/init/scaffolder.py` | Ensure `.lexibrarian.log` and `.lexibrarian.pid` are in `.gitignore` additions |
| `tests/test_config/test_schema.py` | Update `DaemonConfig` field tests |
| `tests/test_config/test_defaults.py` | Update default config assertions |
| `tests/test_daemon/test_service.py` | Rename or replace with `test_service_rewrite.py` |
| `pyproject.toml` | Remove `ignore_errors = true` for `daemon.service` in mypy overrides |

---

## Test Strategy

### `tests/test_utils/test_atomic.py`

- `test_atomic_write_creates_file` -- writes to a new path, verifies content
- `test_atomic_write_overwrites_existing` -- writes over existing file, verifies content
- `test_atomic_write_creates_parent_dirs` -- target in non-existent directory
- `test_atomic_write_no_partial_on_failure` -- simulate write failure (e.g., read-only dir), verify original file unchanged
- `test_atomic_write_same_filesystem` -- temp file is in same directory as target (check no cross-device issues)

### `tests/test_utils/test_conflict.py`

- `test_no_conflict_markers` -- clean file returns `False`
- `test_conflict_markers_present` -- file with `<<<<<<<` returns `True`
- `test_conflict_markers_midline_ignored` -- `<<<<<<<` not at start of line returns `False`
- `test_nonexistent_file` -- missing file returns `False`
- `test_binary_file_tolerant` -- binary content doesn't crash (errors="replace" in open)

### `tests/test_utils/test_locks.py`

- `test_get_lock_returns_same_lock_for_same_dir` -- identity check
- `test_get_lock_returns_different_lock_for_different_dirs` -- identity check
- `test_lock_is_threading_lock` -- type check

### `tests/test_daemon/test_logging.py`

- `test_setup_daemon_logging_creates_log_file` -- log file appears on disk
- `test_log_rotation_config` -- handler has correct `maxBytes` and `backupCount`
- `test_log_level_configurable` -- `"debug"` sets DEBUG, `"warning"` sets WARNING

### `tests/test_daemon/test_service_rewrite.py`

- `test_run_once_skips_when_no_changes` -- mock `_has_changes` returning False, verify no sweep
- `test_run_once_runs_sweep_when_changes` -- mock `_has_changes` returning True, verify sweep runs
- `test_has_changes_no_prior_sweep` -- first run always returns True
- `test_has_changes_detects_newer_file` -- create file with recent mtime, verify True
- `test_has_changes_all_old` -- all files older than last sweep, verify False
- `test_has_changes_skips_lexibrary_dir` -- changes inside `.lexibrary/` don't trigger sweep

### `tests/test_hooks/test_post_commit.py`

- `test_install_creates_hook` -- no existing hook, creates new file
- `test_install_hook_is_executable` -- file permissions include execute
- `test_install_appends_to_existing_hook` -- existing hook preserved, Lexibrarian section appended
- `test_install_idempotent` -- running twice doesn't duplicate
- `test_install_no_git_dir` -- returns error message, doesn't crash
- `test_hook_script_contains_changed_only` -- script text includes `--changed-only`
- `test_hook_script_runs_in_background` -- script text includes `&`

### `tests/test_archivist/test_pipeline_safety.py`

- `test_update_file_skips_conflict_markers` -- file with markers returns failed=True
- `test_update_file_design_hash_recheck` -- simulate agent edit during LLM call, verify LLM output discarded
- `test_atomic_write_used_for_design_files` -- verify `atomic_write` is called (mock check)
- `test_update_files_batch` -- `update_files()` with a list of paths, verify per-file processing
- `test_update_files_skips_deleted_files` -- non-existent paths in list are skipped
- `test_update_files_no_start_here` -- `update_files()` does NOT regenerate START_HERE.md

### `tests/test_cli/test_lexictl.py` (additions)

- `test_update_changed_only` -- `lexictl update --changed-only file1.py file2.py`
- `test_update_changed_only_and_path_mutually_exclusive` -- both provided = error
- `test_sweep_one_shot` -- `lexictl sweep` runs once and exits
- `test_setup_hooks` -- `lexictl setup --hooks` installs hook
- `test_daemon_start_without_watchdog_enabled` -- prints disabled message
- `test_daemon_stop_no_pid` -- prints "not running"
- `test_daemon_status_no_pid` -- prints "not running"

### `tests/test_config/test_schema.py` (additions)

- `test_daemon_config_defaults` -- verify new defaults (3600, True, 5, False, "info")
- `test_daemon_config_old_enabled_field_ignored` -- `enabled: true` in YAML doesn't error (extra="ignore")

---

## Implementation Order

### Step 1: Config & Logging (9a)

1. Update `DaemonConfig` in `src/lexibrarian/config/schema.py`
2. Update default config template in `src/lexibrarian/config/defaults.py`
3. Create `src/lexibrarian/daemon/logging.py`
4. Update config tests in `tests/test_config/test_schema.py` and `tests/test_config/test_defaults.py`
5. Create `tests/test_daemon/test_logging.py`

**Verify:** `uv run pytest tests/test_config/ tests/test_daemon/test_logging.py -v`

### Step 2: Safety Mechanisms (9b)

1. Create `src/lexibrarian/utils/atomic.py`
2. Create `src/lexibrarian/utils/conflict.py`
3. Create `src/lexibrarian/utils/locks.py`
4. Create tests: `test_atomic.py`, `test_conflict.py`, `test_locks.py`

**Verify:** `uv run pytest tests/test_utils/ -v`

### Step 3: Pipeline Extensions (9b + 9c)

1. Update `archivist/pipeline.py`:
   - Replace `write_text()` calls with `atomic_write()`
   - Add conflict marker check before LLM generation in `update_file()`
   - Add D-061 design hash re-check before write in `update_file()`
   - Add `update_files()` function
2. Create `tests/test_archivist/test_pipeline_safety.py`

**Verify:** `uv run pytest tests/test_archivist/ -v`

### Step 4: DaemonService Rewrite (9d)

1. Rewrite `src/lexibrarian/daemon/service.py`
2. Update `src/lexibrarian/daemon/__init__.py`
3. Create `tests/test_daemon/test_service_rewrite.py`
4. Remove `ignore_errors = true` for `daemon.service` in `pyproject.toml` mypy overrides

**Verify:** `uv run pytest tests/test_daemon/ -v && uv run mypy src/lexibrarian/daemon/`

### Step 5: Git Hook Installation (9e)

1. Create `src/lexibrarian/hooks/__init__.py` and `post_commit.py`
2. Create `tests/test_hooks/test_post_commit.py`
3. Update `src/lexibrarian/init/scaffolder.py` -- ensure `.lexibrarian.log` and `.lexibrarian.pid` in gitignore

**Verify:** `uv run pytest tests/test_hooks/ -v`

### Step 6: CLI Commands (9f)

1. Update `lexictl update` with `--changed-only` flag
2. Add `lexictl sweep` command (one-shot + `--watch`)
3. Replace `lexictl daemon` stub with working command
4. Add `--hooks` flag to `lexictl setup`
5. Update CLI tests

**Verify:** `uv run pytest tests/test_cli/test_lexictl.py -v`

### Step 7: Full Verification

1. `uv run pytest --cov=lexibrarian` -- all tests pass
2. `uv run ruff check src/ tests/` -- no lint issues
3. `uv run ruff format src/ tests/` -- formatting clean
4. `uv run mypy src/` -- type checks pass (no more `ignore_errors` for daemon.service)
5. Manual smoke test: `uv run lexictl sweep` runs and exits
6. Manual smoke test: `uv run lexictl setup --hooks` creates git hook
7. Manual smoke test: `uv run lexictl update --changed-only src/lexibrarian/__init__.py` processes one file

### Step 8: Blueprints

1. Update `blueprints/src/lexibrarian/daemon/service.md` -- document rewritten service
2. Create `blueprints/src/lexibrarian/daemon/logging.md`
3. Create `blueprints/src/lexibrarian/hooks/` design files
4. Create `blueprints/src/lexibrarian/utils/atomic.md`
5. Create `blueprints/src/lexibrarian/utils/conflict.md`
6. Update `blueprints/START_HERE.md` with new module descriptions

---

## Risks and Edge Cases

| Risk | Mitigation |
|------|------------|
| `asyncio.run()` nested in threading callback | Each callback creates a fresh event loop. This is the documented pattern and matches `lexictl update` CLI usage. No nested `asyncio.run()` risk as long as callbacks don't call each other. |
| Git hook background process (`&`) fails silently | Output goes to `.lexibrarian.log`. `lexictl status` surfaces stale artifacts. Periodic sweep catches anything hooks miss. |
| Hook appending to existing complex hook (e.g., `husky`) | Marker-based detection prevents duplication. If the existing hook uses a framework, appending is safe -- the Lexibrarian section runs independently. Document that `husky` users should add Lexibrarian to their `.husky/post-commit` instead. |
| `os.replace()` not truly atomic on Windows | Near-atomic on Windows (NTFS supports atomic rename). Acceptable for a dev tool; partial reads are extremely unlikely. |
| Temp file left behind on crash | `finally` block in `atomic_write()` cleans up. `.tmp` suffix files in `.lexibrary/` can be cleaned by future `lexictl validate --fix`. |
| Watchdog import when `watchdog` not installed | Lazy import in `run_watchdog()` means the sweep modes never load `watchdog`. If `watchdog` is missing and user tries daemon mode, they get a clear `ImportError`. |
| `.lexibrarian.log` grows unbounded | `RotatingFileHandler` caps at 5MB with 3 backups (20MB max). |
| Sweep detects changes in `.lexibrary/` causing infinite loop | `_has_changes()` explicitly skips `.lexibrary/` directory. |
| Design hash re-check creates false positives | The re-check only fires when the design file existed before the LLM call AND has a `design_hash` that changed. If the design file was created during the LLM call (by an agent), `pre_llm_design_hash` is `None` and re-check is skipped. |
| `--changed-only` with paths outside scope_root | `update_file()` already checks scope; out-of-scope files return `UNCHANGED` harmlessly. |
| Git amend commits trigger hook again | Correct behaviour -- the amended commit may have different changed files, so re-processing is appropriate. |

---

## What This Phase Does NOT Do

- **No concurrent processing** -- sequential MVP per D-025. Async architecture is in place for future upgrade.
- **No `--dry-run` flag** -- listed in the implementation backlog (Q-005) but deferred.
- **No `lexictl validate --fix`** -- listed in backlog, deferred.
- **No `lexictl update --start-here`** -- independent START_HERE regeneration deferred.
- **No git suppression window for sweep/hook modes** -- D-062 applies only to watchdog mode. Hook mode fires after commit (changes are settled). Sweep mode uses skip-if-unchanged.
- **No hook manager integration** (husky/pre-commit framework) -- append-based approach works alongside them; deeper integration is future work.
- **No CI/CD pipeline templates** -- the master plan shows example YAML but this phase doesn't generate CI config files. Users configure their own CI to call `lexictl validate` and `lexictl update --changed-only`.

---

## What to Watch Out For

1. **The daemon `service.py` has `ignore_errors = true` in mypy overrides.** After the rewrite, remove this suppression and verify the module type-checks cleanly.

2. **The `DaemonConfig.enabled` field is being removed.** Any existing `.lexibrary/config.yaml` with `daemon.enabled: true` will silently ignore the field (`extra="ignore"`). The new `watchdog_enabled: false` field has the opposite default. This is a breaking change but acceptable pre-1.0.

3. **The `crawler/engine.py` is NOT touched by this phase.** It remains broken with `ignore_errors = true`. The daemon no longer calls it. A future cleanup phase should retire or remove it.

4. **The `--changed-only` flag receives file paths from the git hook as shell-expanded arguments.** Typer's `list[Path]` handles this correctly. However, paths with spaces require quoting in the hook script. The current hook script uses unquoted `$changed_files` -- this is the standard shell pattern for `git diff-tree` output (which uses newline-separated paths). Test with paths containing spaces.

5. **`asyncio.run()` cannot be nested.** The daemon callbacks must never be called from within an existing event loop. Since `PeriodicSweep` and `Debouncer` run callbacks in background threads (not in an event loop), this is safe. Do not use `asyncio.run()` anywhere an event loop might already be running.

6. **The periodic sweep's `_has_changes()` uses `os.scandir()` recursively.** For very large projects, this stat walk itself could be slow. However, it's always cheaper than hashing files, and the early return on first changed file limits worst-case traversal.

7. **`.lexibrarian.log` and `.lexibrarian.pid` must be gitignored.** Verify that `lexictl init` scaffolding adds these patterns. If not, the gitignore section in the scaffolder needs updating.

8. **Existing daemon tests (`tests/test_daemon/test_service.py`)** test the broken `DaemonService`. These tests should be replaced rather than updated, since the class interface changes significantly (no more `foreground` parameter, three separate entry points instead of `start()`).

9. **The hook script uses `lexictl` as a bare command.** This assumes `lexictl` is on PATH (installed via `pipx` or `uv tool`). If the user runs it from a virtualenv, the hook may fail. Document that the hook requires `lexictl` to be available in the shell's PATH.

10. **Conflict marker detection only checks for `<<<<<<<`.** This is sufficient for standard git merge conflicts. Other conflict marker formats (e.g., custom merge drivers) are not detected. This is acceptable -- the goal is to catch the common case.
