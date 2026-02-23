## Context

Lexibrary's crawler engine (Phase 5) performs bottom-up directory traversal, generating `.aindex` summary files using LLM calls with SHA-256 change detection. Currently this runs only via the manual `lexi crawl` command. The CLI already has a placeholder `daemon` command (Phase 6) and config schema with `DaemonConfig` (`debounce_seconds`, `sweep_interval_seconds`).

The daemon needs to bridge file system events to the existing crawl engine, keeping `.aindex` files automatically up to date.

## Goals / Non-Goals

**Goals:**
- Automatically re-index when files change, with debouncing to avoid excessive LLM calls
- Provide a periodic full sweep as a safety net for missed events
- Support foreground operation via `lexi daemon --foreground`
- Graceful shutdown on SIGTERM/SIGINT with proper cleanup
- PID file management for lifecycle tracking

**Non-Goals:**
- Background daemonization (fork/detach) — foreground-only for now
- Multi-project watching from a single daemon instance
- Web UI or status API endpoint
- File-level incremental re-indexing (we re-index at the directory level via `full_crawl`)
- Windows service integration

## Decisions

### 1. Use watchdog for file system monitoring
**Choice:** `watchdog` library with its `Observer` pattern.
**Rationale:** watchdog is the standard Python file system monitoring library, supports macOS (FSEvents), Linux (inotify), and Windows (ReadDirectoryChangesW) natively. It handles cross-platform differences transparently.
**Alternatives:** `inotifyx` (Linux-only), polling (wasteful), `asyncio` file watchers (less mature).

### 2. Single global debounce timer (not per-directory)
**Choice:** One `threading.Timer` that resets on any event, collecting all affected directories into a set.
**Rationale:** During active editing, changes often span multiple directories (e.g., editing source + tests). A single timer coalesces all activity into one batch, reducing redundant crawls. Per-directory timers would cause partial re-indexes that miss cross-directory consistency.
**Alternatives:** Per-directory timers (more granular but more complex and potentially wasteful), queue-based batching (unnecessary complexity for this use case).

### 3. Reuse `full_crawl()` for both incremental and sweep operations
**Choice:** Call the existing `full_crawl()` engine for all re-indexing. The SHA-256 change detection already handles skipping unchanged files, making it efficient even when called for the full tree.
**Rationale:** Avoids duplicating crawl logic. The change detector cache means a "full crawl" is effectively incremental — only changed files get re-summarized. This simplifies the daemon significantly.
**Alternatives:** Directory-scoped incremental crawl function (would need new engine API, risk divergence from main crawl logic).

### 4. Threading model: watchdog threads + Timer threads + asyncio.run() for LLM
**Choice:** Let watchdog manage its own observer threads. Debouncer and sweep use `threading.Timer` (daemon threads). LLM calls run via `asyncio.run()` inside the callback thread.
**Rationale:** The crawler engine uses async for LLM calls. Since callbacks fire from timer threads (not the main thread), `asyncio.run()` creates a temporary event loop per callback invocation. This avoids the complexity of running a persistent event loop. Main thread simply blocks on `shutdown_event.wait()`.
**Alternatives:** Persistent asyncio event loop on main thread (more complex signal handling), thread pool executor (unnecessary indirection).

### 5. Use `OutputConfig` filenames for internal file filtering
**Choice:** The event handler filters `.aindex` files by prefix and internal files (cache, log, pid) by exact name, referencing the configured filenames.
**Rationale:** Prevents infinite re-indexing loops where daemon writes trigger more daemon events. These filenames are defined in `OutputConfig` and `DaemonConfig`.

## Risks / Trade-offs

- **[Missed events on high-volume changes]** → watchdog can drop events under extreme load. Mitigated by periodic full sweep acting as a safety net.
- **[LLM rate limits during rapid re-indexing]** → Debouncing reduces frequency, but bursts of changes after a quiet period could trigger many LLM calls. Mitigated by the change detector cache (only truly changed files get re-summarized).
- **[Race condition: concurrent crawls]** → If a debounced re-index is running when the periodic sweep fires, both could modify the same `.aindex` files. Mitigated by keeping sweep intervals long (default 300s) and the debounce callback being quick for cached content. Future improvement: add a mutex around crawl operations.
- **[No daemonization]** → Foreground-only means the user must keep a terminal open or use external tools (systemd, launchd, screen). Acceptable for initial implementation; background mode can be added later.
