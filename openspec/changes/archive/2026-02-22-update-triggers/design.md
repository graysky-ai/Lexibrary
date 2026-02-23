## Context

The archivist pipeline (`update_file()`, `update_project()` in `archivist/pipeline.py`) is the correct, functional update engine. However, the `DaemonService` in `daemon/service.py` is wired to the retired `full_crawl()` from `crawler/engine.py` and references non-existent config fields (`config.output.log_filename`, `config.output.cache_filename`, `config.tokenizer`). The daemon module has `ignore_errors = true` in mypy overrides.

Currently, the only way to trigger library updates is manual `lexictl update`. There is no automated trigger — no git hooks, no working periodic sweep, no CI integration. The pipeline also lacks safety mechanisms: writes to `.lexibrary/` use direct `Path.write_text()` (non-atomic), there is no conflict marker detection, and no protection against overwriting agent edits during LLM generation.

The existing `Debouncer`, `PeriodicSweep`, and `LexibraryEventHandler` in the daemon package are clean and reusable. The `DaemonConfig` schema needs updating: `enabled` replaced with `watchdog_enabled` (default `False`), new fields for sweep-skip-if-unchanged, git suppression, and logging.

## Goals / Non-Goals

**Goals:**
- Deliver automated library maintenance via git hooks (primary trigger), periodic sweep (safety net), and CI-compatible `--changed-only` mode
- Rewrite `DaemonService` to use the archivist pipeline instead of retired `full_crawl()`
- Add safety mechanisms (atomic writes, conflict marker detection, design hash re-check) that protect all trigger modes
- Deprecate the watchdog daemon (off by default, retained for opt-in)
- Remove mypy `ignore_errors` suppression for `daemon.service`

**Non-Goals:**
- No concurrent processing — sequential MVP per D-025. Async architecture in place for future upgrade.
- No `--dry-run` flag (backlog Q-005)
- No `lexictl validate --fix` (backlog)
- No CI/CD pipeline template generation — users configure their own CI to call `lexictl validate` and `lexictl update --changed-only`
- No hook manager integration (husky/pre-commit framework) — append-based approach works alongside them
- No git suppression window for sweep/hook modes (D-062 applies only to watchdog mode)

## Decisions

### D1: Atomic writes via temp-file + `os.replace()`

All writes to `.lexibrary/` SHALL use a new `atomic_write()` utility that creates a temp file in the same directory as the target, writes content, then calls `os.replace()`. This is atomic on POSIX and near-atomic on Windows (NTFS supports atomic rename).

**Why not direct `write_text()`:** An agent reading via `lexi lookup` during a write could see a partial file. With `os.replace()`, readers see either the old or new version, never a partial write.

**Alternative considered:** File locking (`fcntl.flock`). Rejected because it doesn't protect against crashes mid-write, and `os.replace()` is simpler and more robust.

### D2: Conflict marker detection before LLM generation

Before invoking the Archivist on a changed source file, the engine SHALL check for git conflict markers (`<<<<<<<` at start of line). Files with unresolved merge conflicts are skipped and logged as warnings.

**Why:** Sending conflicted files to the LLM produces garbage output and wastes API calls.

### D3: Design hash re-check (TOCTOU protection)

After LLM generation completes and before writing the result, `update_file()` SHALL re-read the design file's `design_hash` and compare against the hash recorded before the LLM call. If they differ, an agent edited the file during the LLM call — discard the LLM output.

**Why:** Closes the race condition in the agent-first authoring model (D-019). Without this, the Archivist could overwrite an agent's recent edits.

### D4: Three-mode DaemonService

The rewritten `DaemonService` SHALL have three entry points:
1. `run_once()` — single sweep, process pending changes, exit
2. `run_watch()` — periodic sweeps in foreground until interrupted
3. `run_watchdog()` — deprecated real-time file watching (requires `watchdog_enabled: true`)

**Why separate modes instead of a single `start()`:** The old `start()` combined everything. Separating modes makes each independently testable and allows the CLI to expose them as distinct commands (`lexictl sweep` vs `lexictl sweep --watch` vs `lexictl daemon`).

### D5: Skip-if-unchanged sweep optimization

Before running a scheduled sweep, the engine SHALL scan `scope_root` for any file with `mtime` newer than the last sweep timestamp using `os.scandir()` stat walk. If nothing changed, skip the sweep entirely.

**Why `os.scandir()` over hashing:** Stat walks are orders of magnitude cheaper than hashing. The scan returns early on the first changed file, so best-case is O(1). The sweep interval becomes a maximum; sweeps only fire when there's actual work.

### D6: Git post-commit hook as primary trigger

`lexictl setup --hooks` SHALL install a `post-commit` hook (not `pre-commit`) that runs `lexictl update --changed-only $files` in the background. Post-commit because the library should never block code delivery.

**Why not pre-commit:** Pre-commit hooks block the commit. Library updates involve LLM calls that can take seconds to minutes — this would be unacceptable UX.

**Alternative considered:** Pre-push hook. Rejected because it fires too late — the library would be stale between commit and push.

### D7: `update_files()` batch function

A new `update_files()` function in `archivist/pipeline.py` SHALL process a specific list of file paths, skipping non-existent (deleted), binary, and ignored files. It does NOT regenerate `START_HERE.md` — that is a full-project concern handled by `update_project()`.

**Why a separate function vs. filtering in `update_project()`:** `update_project()` discovers files via `rglob("*")`. For git hooks, we already know exactly which files changed — discovery is unnecessary overhead.

### D8: Watchdog imports are lazy

The `watchdog` library SHALL only be imported when `run_watchdog()` is called. Sweep modes work without `watchdog` installed. If `watchdog` is missing and a user tries daemon mode, they get a clear `ImportError`.

**Why:** `watchdog` is a heavyweight optional dependency. Most users will use git hooks + sweep, not the deprecated watchdog mode.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| `asyncio.run()` nested in threading callback | Each callback creates a fresh event loop. This is the documented pattern and matches `lexictl update` CLI usage. No nested `asyncio.run()` risk as long as callbacks don't call each other. |
| Git hook background process (`&`) fails silently | Output goes to `.lexibrary.log`. `lexictl status` surfaces stale artifacts. Periodic sweep catches anything hooks miss. |
| Hook appending to existing complex hook (e.g., husky) | Marker-based detection prevents duplication. If the existing hook uses a framework, appending is safe. Document that `husky` users should add Lexibrary to their `.husky/post-commit` instead. |
| Temp file left behind on crash | `finally` block in `atomic_write()` cleans up. `.tmp` suffix files in `.lexibrary/` can be cleaned by future `lexictl validate --fix`. |
| `.lexibrary.log` grows unbounded | `RotatingFileHandler` caps at 5MB with 3 backups (20MB max). |
| Sweep detects changes in `.lexibrary/` causing infinite loop | `_has_changes()` explicitly skips `.lexibrary/` directory. |
| `--changed-only` with paths outside scope_root | `update_file()` already checks scope; out-of-scope files return `UNCHANGED` harmlessly. |
| Hook script uses bare `lexictl` command | Requires `lexictl` on PATH (installed via `pipx` or `uv tool`). Document this requirement. |
| `DaemonConfig.enabled` removal | Pre-1.0 breaking change. `extra="ignore"` silently drops the old field. `watchdog_enabled` replaces it with opposite default. |

## Open Questions

None — all design questions for Phase 9 were resolved in decisions D-059 through D-067 (see `plans/v2-master-plan.md`). The implementation follows those decisions directly.
