## Why

Lexibrary currently requires manual `lexi crawl` invocations to update `.aindex` files. For projects under active development, this creates stale indexes. A background daemon that watches for file changes and automatically re-indexes keeps `.aindex` files fresh without user intervention.

## What Changes

- Add a background daemon service (`lexi daemon --foreground`) that watches the project directory for file changes using `watchdog`
- Implement debounced incremental re-indexing: rapid file changes are coalesced into batched re-index operations rather than triggering per-event
- Add periodic full sweep as a safety net to catch any changes missed by the file watcher
- Implement graceful shutdown via SIGTERM/SIGINT signal handling
- Write/remove a PID file (`.lexibrary.pid`) for daemon lifecycle tracking
- Wire the existing `daemon` CLI command (Phase 6) to the new daemon service

## Capabilities

### New Capabilities
- `file-watching`: Watchdog-based file system event handler that filters ignored files, `.aindex` files, and Lexibrary internal files, then forwards affected directories to the debouncer
- `debouncing`: Timer-based event coalescing that accumulates changed directories and fires a single re-index callback after a configurable quiet period
- `periodic-sweep`: Scheduled full crawl at configurable intervals as a safety net for missed file system events
- `daemon-lifecycle`: Service orchestrator managing startup, PID file, signal handlers, watcher/debouncer/sweep coordination, and graceful shutdown

### Modified Capabilities
- `cli-skeleton`: The existing `daemon` command group needs to be wired to the new `DaemonService`

## Impact

- **New package:** `src/lexibrary/daemon/` with modules: `watcher.py`, `debouncer.py`, `scheduler.py`, `service.py`
- **New dependency:** `watchdog` (file system event monitoring)
- **Config:** Uses existing `daemon` section of `LexibraryConfig` (`debounce_seconds`, `full_sweep_interval_minutes`, `log_file`)
- **Integrations:** Calls `full_crawl()` from Phase 5 crawler engine; uses `IgnoreMatcher`, `ChangeDetector`, tokenizer, and LLM service
- **Phase:** Phase 7 (depends on Phase 1 config/ignore/utils, Phase 5 crawler engine, Phase 6 CLI wiring)
