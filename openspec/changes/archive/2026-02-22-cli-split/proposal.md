## Why

The single `lexi` CLI currently exposes both agent-facing commands (lookup, search, concepts, stack) and maintenance commands (init, update, validate, status) in one entry point. This violates the maintenance service pattern (D-051): agents can accidentally trigger expensive operations like `lexi update` (LLM calls) or `lexi init` (directory creation) during coding sessions. Splitting into two CLIs (`lexi` for agents, `lexictl` for maintenance) enforces the separation at the tool boundary, as specified in the architecture overview (sections 8-9) and decisions D-052, D-056.

## What Changes

- **BREAKING**: The single `lexi` CLI is split into two entry points: `lexi` (agent-facing) and `lexictl` (setup/maintenance)
- **BREAKING**: `lexi init`, `lexi update`, `lexi validate`, `lexi status`, `lexi setup`, and `lexi daemon` no longer exist — they become `lexictl init`, `lexictl update`, `lexictl validate`, `lexictl status`, `lexictl setup`, `lexictl daemon`
- **BREAKING**: The `lexibrary` command alias is dropped (pre-1.0, no backwards-compatibility obligation)
- **BREAKING**: Import path changes: `from lexibrary.cli import app` no longer works — use `from lexibrary.cli import lexi_app` or `lexictl_app`
- The monolithic `src/lexibrary/cli.py` file is replaced by a `src/lexibrary/cli/` package with `__init__.py`, `_shared.py`, `lexi_app.py`, `lexictl_app.py`
- All cross-reference strings in source code updated (e.g., `"lexi init"` → `"lexictl init"` in error messages)
- Test file `tests/test_cli.py` split into `tests/test_cli/test_lexi.py` and `tests/test_cli/test_lexictl.py`
- Entry points in `pyproject.toml` updated: `lexi` → `lexibrary.cli:lexi_app`, `lexictl` → `lexibrary.cli:lexictl_app`
- Blueprint design files updated to reflect the new package structure

## Capabilities

### New Capabilities

- `cli-package-structure`: The `cli/` package layout with shared helpers module (`_shared.py`), agent-facing app (`lexi_app.py`), and maintenance app (`lexictl_app.py`). Covers the `__init__.py` re-exports and shared helper functions (`console`, `require_project_root()`, `stub()`).
- `lexictl-entry-point`: The `lexictl` maintenance CLI entry point — Typer app definition, command registration (init, update, validate, status, setup, daemon), and `pyproject.toml` script entry.

### Modified Capabilities

- `cli-skeleton`: The Typer app definition changes from a single `app` to two apps (`lexi_app`, `lexictl_app`). The `lexibrary` alias is removed. `__main__.py` imports `lexi_app` instead of `app`.
- `cli-commands`: Commands are redistributed between two CLIs. Agent-facing commands (lookup, index, describe, concepts, stack, search) stay on `lexi`. Maintenance commands (init, update, validate, status, setup, daemon) move to `lexictl`. All cross-reference strings updated.
- `project-scaffolding`: Entry points in `pyproject.toml` change. The `src/lexibrary/cli.py` file is replaced by a `cli/` package directory.

## Impact

- **Source files changed**: `pyproject.toml`, `src/lexibrary/__main__.py`, `src/lexibrary/validator/checks.py`, `src/lexibrary/init/scaffolder.py`, `src/lexibrary/config/defaults.py`, `src/lexibrary/daemon/service.py`
- **Source files deleted**: `src/lexibrary/cli.py`
- **Source files created**: `src/lexibrary/cli/__init__.py`, `src/lexibrary/cli/_shared.py`, `src/lexibrary/cli/lexi_app.py`, `src/lexibrary/cli/lexictl_app.py`
- **Test files deleted**: `tests/test_cli.py`
- **Test files created**: `tests/test_cli/__init__.py`, `tests/test_cli/test_lexi.py`, `tests/test_cli/test_lexictl.py`
- **Test files modified**: `tests/test_validator/test_warning_checks.py`, `tests/test_validator/test_report.py`
- **Blueprints**: `blueprints/src/lexibrary/cli.md` replaced by `blueprints/src/lexibrary/cli/__init__.md`, `blueprints/src/lexibrary/cli/_shared.md`, `blueprints/src/lexibrary/cli/lexi_app.md`, `blueprints/src/lexibrary/cli/lexictl_app.md`; `blueprints/START_HERE.md` updated for new package structure
- **No new dependencies** — purely structural refactor within Phase 8a
- **Post-change**: Must run `uv sync` to re-register entry points
