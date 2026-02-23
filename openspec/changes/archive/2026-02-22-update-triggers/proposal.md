## Why

The `DaemonService` is non-functional: it references retired APIs (`full_crawl()`, `config.output.*`, `config.tokenizer`) that no longer exist in the codebase. The archivist pipeline (`update_file()`, `update_project()`) is the correct update engine but lacks safety mechanisms (atomic writes, conflict detection, design hash re-check) and a `--changed-only` mode needed for git hook integration. There is no automated trigger for library maintenance beyond manual `lexictl update` — the project needs git hooks (primary), periodic sweep (safety net), and CI integration to keep the library current without human intervention.

## What Changes

- **Rewrite `DaemonService`** to use the archivist pipeline (`update_project()`, `update_files()`) instead of the retired `full_crawl()`. Three entry points: `run_once()` (one-shot sweep), `run_watch()` (periodic), `run_watchdog()` (deprecated real-time).
- **Update `DaemonConfig`**: remove `enabled` field, add `sweep_skip_if_unchanged`, `git_suppression_seconds`, `watchdog_enabled` (default `False`), `log_level`; change `sweep_interval_seconds` default from 300 to 3600. **BREAKING** (pre-1.0, acceptable).
- **Add atomic writes** for all `.lexibrary/` file writes (temp file + `os.replace()`).
- **Add conflict marker detection** — skip source files with git merge conflict markers before LLM generation.
- **Add design hash re-check (D-061)** — discard LLM output if an agent edited the design file during generation.
- **Add `update_files()` batch function** and `--changed-only` flag to `lexictl update` for processing specific files (git hooks, CI).
- **Add `lexictl setup --hooks`** to install a git post-commit hook that runs `lexictl update --changed-only` in the background.
- **Add `lexictl sweep` command** (one-shot + `--watch` mode).
- **Replace `lexictl daemon` stub** with a working (but deprecated) watchdog command.
- **Add daemon-specific logging** with `RotatingFileHandler` to `.lexibrary.log`.
- **Add per-directory `.aindex` write locks** for future concurrency safety.
- **Remove `ignore_errors = true`** for `daemon.service` in pyproject.toml mypy overrides.

## Capabilities

### New Capabilities
- `atomic-writes`: Atomic file write utility using temp-file + `os.replace()` for all `.lexibrary/` writes
- `conflict-detection`: Git merge conflict marker detection to skip files with unresolved conflicts
- `design-hash-recheck`: Re-check `design_hash` after LLM generation before write, discarding output if agent edited during LLM call
- `aindex-write-locks`: Per-directory write locks for `.aindex` serialisation (no-op under sequential MVP)
- `daemon-logging`: Daemon-specific `RotatingFileHandler` setup for `.lexibrary.log`
- `daemon-rewrite`: Complete rewrite of `DaemonService` with three modes: one-shot sweep, periodic watch, deprecated watchdog
- `changed-only-pipeline`: `update_files()` batch function and `--changed-only` CLI flag for processing specific file lists
- `git-hook-installation`: `lexictl setup --hooks` for installing git post-commit hook
- `sweep-command`: `lexictl sweep` command (one-shot and `--watch` mode)
- `daemon-command`: Working `lexictl daemon start|stop|status` command (deprecated, replaces stub)

### Modified Capabilities
- `config-system`: `DaemonConfig` schema changes — new fields, removed `enabled`, changed default for `sweep_interval_seconds`
- `archivist-pipeline`: Add `update_files()`, adopt atomic writes, add conflict marker check, add design hash re-check
- `daemon-lifecycle`: Complete rewrite — new interface, new dependencies, new entry points
- `periodic-sweep`: Integration with skip-if-unchanged logic and archivist pipeline

## Impact

- **Config schema** (`config/schema.py`, `config/defaults.py`): `DaemonConfig` field changes — breaking for any existing config with `daemon.enabled` (silently ignored via `extra="ignore"`)
- **Archivist pipeline** (`archivist/pipeline.py`): Four `write_text()` calls replaced with `atomic_write()`, new `update_files()` function, conflict marker check and design hash re-check added to `update_file()`
- **Daemon module** (`daemon/service.py`): Complete rewrite — new class interface
- **CLI** (`cli/lexictl_app.py`): `update` gains `--changed-only`, `setup` gains `--hooks`, new `sweep` command, `daemon` stub replaced
- **New modules**: `utils/atomic.py`, `utils/conflict.py`, `utils/locks.py`, `daemon/logging.py`, `hooks/__init__.py`, `hooks/post_commit.py`
- **Init scaffolder** (`init/scaffolder.py`): Ensure `.lexibrary.log` and `.lexibrary.pid` in `.gitignore`
- **pyproject.toml**: Remove `ignore_errors = true` for `daemon.service`
- **Blueprints**: Multiple existing blueprints need updating, new blueprints for new modules
- **No new dependencies**: All functionality uses stdlib (`tempfile`, `os.replace`, `threading`, `logging.handlers`, `stat`)
