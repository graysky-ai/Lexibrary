## Context

The current codebase has a single `cli.py` file (~1,340 lines) that defines one Typer app exposing all commands under `lexi`. The architecture overview (sections 8-9) and decisions D-051, D-052, D-056 call for two CLIs: `lexi` (agent-facing) and `lexictl` (maintenance). This change is purely structural — no new functionality, no new dependencies.

Current state:
- `src/lexibrary/cli.py` — monolithic file with all commands
- `pyproject.toml` — two entry points (`lexi`, `lexibrary`) both pointing to `lexibrary.cli:app`
- `src/lexibrary/__main__.py` — imports `app` from `lexibrary.cli`
- `tests/test_cli.py` — single test file for all CLI tests

## Goals / Non-Goals

**Goals:**
- Split `cli.py` into a `cli/` package with two Typer apps and shared helpers
- Register `lexi` and `lexictl` as separate entry points in `pyproject.toml`
- Update all cross-reference strings (error messages, help text, suggestions) to point to the correct CLI
- Split tests to match the new structure
- Update blueprints to reflect the new package layout

**Non-Goals:**
- No new commands or functionality
- No changes to command signatures or behavior (beyond help text/messages)
- No init wizard (Phase 8b)
- No agent rules or IWH system (Phase 8c)
- No backwards-compatibility aliases for `from lexibrary.cli import app`

## Decisions

### D1: Package with shared helpers (not two files in one module)

Split into a `cli/` package with four files rather than keeping two apps in one file.

**Chosen**: `cli/__init__.py` + `cli/_shared.py` + `cli/lexi_app.py` + `cli/lexictl_app.py`
**Alternative**: Two Typer apps in a single `cli.py` — rejected because it preserves the monolith problem and future phases (8b, 8c) will add significant logic to `lexictl_app.py`.

**Rationale**: Clean separation of concerns, each app file contains only its own commands, shared helpers live in one place.

### D2: Stack helpers stay in `lexi_app.py`

`_stack_dir()`, `_next_stack_id()`, `_slugify()`, `_find_post_path()` are used exclusively by stack commands. They move to `lexi_app.py` as private functions, not to `_shared.py`.

### D3: Drop the `lexibrary` command alias

Pre-1.0, no backwards-compatibility obligation. Two CLIs (`lexi`, `lexictl`) provide clear naming. A third name adds confusion.

### D4: `__main__.py` runs `lexi_app`

`python -m lexibrary` runs the agent-facing CLI since that is the primary use case.

### D5: Drop leading underscores on shared helpers

`_require_project_root()` → `require_project_root()` and `_stub()` → `stub()` since they are now module-level exports in `_shared.py`, not private functions within a single file.

### D6: Test file split mirrors source split

`tests/test_cli.py` → `tests/test_cli/test_lexi.py` + `tests/test_cli/test_lexictl.py` with an `__init__.py`. `TestNoProjectRoot` is split across both files. `TestHelp` is rewritten for each app.

## Risks / Trade-offs

- **Import path break** → `from lexibrary.cli import app` no longer works. Pre-1.0, acceptable. Mitigation: clear error at import time (AttributeError on missing `app`).
- **`lexi init` no longer exists** → Running `lexi init` produces Typer "No such command" error. Mitigation: `require_project_root()` error message directs to `lexictl init`.
- **Test runner discovery** → Moving from `test_cli.py` to `test_cli/` package requires `__init__.py`. Pytest with `testpaths = ["tests"]` discovers automatically.
- **Stale mental models** → Contributors accustomed to `lexi update` or `lexi validate`. Mitigation: error messages consistently reference `lexictl`.
