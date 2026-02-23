## 1. Config Schema & Defaults

- [x] 1.1 Update `DaemonConfig` in `src/lexibrary/config/schema.py`: remove `enabled` field, add `sweep_skip_if_unchanged`, `git_suppression_seconds`, `watchdog_enabled`, `log_level`; change `sweep_interval_seconds` default to 3600
- [x] 1.2 Update `DEFAULT_PROJECT_CONFIG_TEMPLATE` in `src/lexibrary/config/defaults.py` to reflect new daemon fields
- [x] 1.3 Update config tests in `tests/test_config/test_schema.py` for new `DaemonConfig` defaults and `enabled` field ignored
- [x] 1.4 Update config tests in `tests/test_config/test_defaults.py` for new default config template

## 2. Safety Utilities

- [x] 2.1 Create `src/lexibrary/utils/atomic.py` with `atomic_write()` function (temp-file + `os.replace()`)
- [x] 2.2 Create `src/lexibrary/utils/conflict.py` with `has_conflict_markers()` function
- [x] 2.3 Create `src/lexibrary/utils/locks.py` with `DirectoryLockManager` class
- [x] 2.4 Create `tests/test_utils/test_atomic.py` — test atomic write create, overwrite, parent dirs, failure cleanup, same-dir temp
- [x] 2.5 Create `tests/test_utils/test_conflict.py` — test clean file, markers present, midline ignored, nonexistent file, binary tolerance
- [x] 2.6 Create `tests/test_utils/test_locks.py` — test same lock for same dir, different locks for different dirs, lock type

## 3. Daemon Logging

- [x] 3.1 Create `src/lexibrary/daemon/logging.py` with `setup_daemon_logging()` function (RotatingFileHandler)
- [x] 3.2 Create `tests/test_daemon/test_logging.py` — test log file creation, rotation config, configurable log level

## 4. Pipeline Safety Extensions

- [x] 4.1 Add conflict marker check to `update_file()` in `archivist/pipeline.py` — call `has_conflict_markers()` before LLM generation, return `FileResult(failed=True)` if detected
- [x] 4.2 Add design hash re-check (D-061) to `update_file()` — capture `pre_llm_design_hash` before LLM call, re-check after generation, discard if changed
- [x] 4.3 Replace all `Path.write_text()` calls in `archivist/pipeline.py` with `atomic_write()` (4 call sites: lines ~114, ~146, ~185, ~320)
- [x] 4.4 Add `update_files()` batch function to `archivist/pipeline.py` for processing a specific list of files
- [x] 4.5 Create `tests/test_archivist/test_pipeline_safety.py` — test conflict marker skip, design hash re-check, atomic write usage, batch update, deleted files skip, no START_HERE regeneration

## 5. DaemonService Rewrite

- [x] 5.1 Rewrite `src/lexibrary/daemon/service.py` — three entry points (`run_once`, `run_watch`, `run_watchdog`), use archivist pipeline, skip-if-unchanged, lazy watchdog imports
- [x] 5.2 Update `src/lexibrary/daemon/__init__.py` exports if needed
- [x] 5.3 Create `tests/test_daemon/test_service_rewrite.py` — test run_once skip/run, has_changes first run/newer file/all old/skip lexibrary dir
- [x] 5.4 Remove `ignore_errors = true` for `lexibrary.daemon.service` in `pyproject.toml` mypy overrides

## 6. Git Hook Installation

- [x] 6.1 Create `src/lexibrary/hooks/__init__.py` (empty package init)
- [x] 6.2 Create `src/lexibrary/hooks/post_commit.py` with `install_post_commit_hook()` and hook script template
- [x] 6.3 Create `tests/test_hooks/__init__.py` (empty test package init)
- [x] 6.4 Create `tests/test_hooks/test_post_commit.py` — test create hook, executable permissions, append to existing, idempotent, no git dir, script content
- [x] 6.5 Update `src/lexibrary/init/scaffolder.py` to ensure `.lexibrary.log` and `.lexibrary.pid` are in gitignore additions

## 7. CLI Commands

- [x] 7.1 Update `lexictl update` in `cli/lexictl_app.py` to accept `--changed-only` flag (list of paths), call `update_files()`, error if both `path` and `--changed-only` provided
- [x] 7.2 Add `--hooks` flag to `lexictl setup` in `cli/lexictl_app.py`, call `install_post_commit_hook()`
- [x] 7.3 Add `lexictl sweep` command to `cli/lexictl_app.py` (one-shot + `--watch` mode)
- [x] 7.4 Replace `lexictl daemon` stub with working command (start/stop/status actions) in `cli/lexictl_app.py`
- [x] 7.5 Update CLI tests in `tests/test_cli/test_lexictl.py` — test `--changed-only`, mutual exclusivity, sweep one-shot, setup --hooks, daemon start/stop/status

## 8. Blueprints

- [x] 8.1 Update `blueprints/src/lexibrary/daemon/service.md` — document rewritten DaemonService interface, dependencies, key concepts
- [x] 8.2 Create `blueprints/src/lexibrary/daemon/logging.md` — document setup_daemon_logging
- [x] 8.3 Create `blueprints/src/lexibrary/utils/atomic.md` — document atomic_write
- [x] 8.4 Create `blueprints/src/lexibrary/utils/conflict.md` — document has_conflict_markers
- [x] 8.5 Create `blueprints/src/lexibrary/utils/locks.md` — document DirectoryLockManager
- [x] 8.6 Create `blueprints/src/lexibrary/hooks/` directory with `post_commit.md`
- [x] 8.7 Update `blueprints/src/lexibrary/archivist/pipeline.md` — document update_files, conflict check, design hash re-check, atomic writes
- [x] 8.8 Update `blueprints/src/lexibrary/config/schema.md` — document new DaemonConfig fields
- [x] 8.9 Update `blueprints/src/lexibrary/config/defaults.md` — document updated daemon section
- [x] 8.10 Update `blueprints/src/lexibrary/cli/lexictl_app.md` — document new commands and flags
- [x] 8.11 Update `blueprints/src/lexibrary/init/scaffolder.md` — document gitignore additions
- [x] 8.12 Update `blueprints/START_HERE.md` — add new modules to topology and package map

## 9. Full Verification

- [x] 9.1 Run `uv run pytest --cov=lexibrary` — all tests pass
- [x] 9.2 Run `uv run ruff check src/ tests/` — no lint issues
- [x] 9.3 Run `uv run ruff format src/ tests/` — formatting clean
- [x] 9.4 Run `uv run mypy src/` — type checks pass (no more `ignore_errors` for daemon.service)
