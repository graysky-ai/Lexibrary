# Phase 8a -- CLI Split: Implementation Plan

**Reference:** `plans/v2-master-plan.md` (Phase 8a section), `lexibrary-overview.md` (section 9)
**Depends on:** Phase 7 (Validation & Status) — all existing commands implemented
**Consumed by:** Phase 8b (Init Wizard), Phase 8c (Agent Rules + IWH)

---

## Goal

Split the single `lexi` CLI into two separate entry points:
- **`lexi`** -- agent-facing commands for day-to-day coding (lookup, index, search, concepts, stack, describe)
- **`lexictl`** -- setup and maintenance commands (init, update, validate, status, setup, daemon)

This is a purely structural change. No new functionality is introduced. Command implementations move between CLIs, and both share the same underlying modules. Implements design decisions D-051, D-052, D-056.

---

## 1. File Structure: Convert `cli.py` to a `cli/` Package

### Decision: Package with Shared Helpers

The current `src/lexibrary/cli.py` is a single 1,340-line file. Rather than keeping two Typer apps in one file (which would remain a monolith and be difficult to navigate), split into a `cli/` package with three modules:

```
src/lexibrary/cli/
    __init__.py          # Re-exports: lexi_app, lexictl_app
    _shared.py           # Shared helpers: console, require_project_root(), stub()
    lexi_app.py          # Agent-facing Typer app + all agent commands
    lexictl_app.py       # Maintenance Typer app + all maintenance commands
```

### Rationale

- Clean separation of concerns: each app file contains only its own commands
- Shared helpers (`console`, `require_project_root()`, `stub()`) live in one place, imported by both apps
- Preserves the lazy import pattern already used throughout the current `cli.py`
- Future phases (8b, 8c) will add significant logic to `lexictl_app.py` (init wizard, setup update); having it as a separate file prevents further bloat

### Migration Steps

**Step 1: Create `src/lexibrary/cli/__init__.py`**

```python
"""CLI package for Lexibrary — two entry points."""

from __future__ import annotations

from lexibrary.cli.lexi_app import app as lexi_app
from lexibrary.cli.lexictl_app import app as lexictl_app

__all__ = ["lexi_app", "lexictl_app"]
```

**Step 2: Create `src/lexibrary/cli/_shared.py`**

Extract from the current `cli.py`:
- `console = Console()` (module-level Rich console)
- `require_project_root()` function (renamed from `_require_project_root`)
- `stub()` function (renamed from `_stub`)
- Top-level imports needed by helpers

```python
"""Shared helpers for both lexi and lexictl CLIs."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from lexibrary.exceptions import LexibraryNotFoundError
from lexibrary.utils.root import find_project_root

console = Console()


def require_project_root() -> Path:
    """Resolve the project root or exit with a friendly error."""
    try:
        return find_project_root()
    except LexibraryNotFoundError:
        console.print(
            "[red]No .lexibrary/ directory found.[/red] "
            "Run [cyan]lexictl init[/cyan] to create one."
        )
        raise typer.Exit(1) from None


def stub(name: str) -> None:
    """Print a standard stub message for unimplemented commands."""
    require_project_root()
    console.print(f"[yellow]Not yet implemented.[/yellow]  ([dim]{name}[/dim])")
```

Note the two changes from current code:
1. The error message in `require_project_root()` changes from `"Run [cyan]lexi init[/cyan]"` to `"Run [cyan]lexictl init[/cyan]"` (init moves to `lexictl`).
2. The leading underscore is dropped from the function names (`require_project_root` and `stub`) since they are now module-level exports in a shared module rather than private functions within a single file.

**Step 3: Create `src/lexibrary/cli/lexi_app.py`**

Move from current `cli.py`:
- `lookup` command
- `index` command
- `describe` command
- `concepts` command
- `concept_app` sub-group with `concept_new` and `concept_link`
- `stack_app` sub-group with all stack commands (`post`, `search`, `answer`, `vote`, `accept`, `view`, `list`)
- `search` command
- Stack helper functions: `_stack_dir()`, `_next_stack_id()`, `_slugify()`, `_find_post_path()`

The Typer app definition:

```python
app = typer.Typer(
    name="lexi",
    help=(
        "Agent-facing CLI for Lexibrary. "
        "Lookups, search, concepts, and Stack Q&A for day-to-day coding."
    ),
    no_args_is_help=True,
)
```

**Step 4: Create `src/lexibrary/cli/lexictl_app.py`**

Move from current `cli.py`:
- `init` command
- `update` command
- `validate` command
- `status` command
- `setup` command (stub)
- `daemon` command (stub)

The Typer app definition:

```python
app = typer.Typer(
    name="lexictl",
    help=(
        "Maintenance CLI for Lexibrary. "
        "Project setup, design file generation, validation, and daemon management."
    ),
    no_args_is_help=True,
)
```

**Step 5: Delete `src/lexibrary/cli.py`**

The old file is fully replaced by the package.

**Step 6: Update `src/lexibrary/__main__.py`**

Change to:
```python
from lexibrary.cli import lexi_app

if __name__ == "__main__":
    lexi_app()
```

The `__main__.py` module (invoked via `python -m lexibrary`) should run the agent-facing CLI, since that is the primary use case.

---

## 2. Entry Points: `pyproject.toml` Changes

### Current

```toml
[project.scripts]
lexi = "lexibrary.cli:app"
lexibrary = "lexibrary.cli:app"
```

### New

```toml
[project.scripts]
lexi = "lexibrary.cli:lexi_app"
lexictl = "lexibrary.cli:lexictl_app"
```

### Decision: Drop the `lexibrary` Alias

The `lexibrary` alias currently maps to the same app as `lexi`. It should be **dropped**:
- Pre-1.0, no backwards-compatibility obligation.
- Two CLIs already provide clear naming (`lexi` for agents, `lexictl` for maintenance).
- A third name adds confusion with no benefit.
- The overview document and master plan never reference a `lexibrary` command -- only `lexi` and `lexictl`.

After changing `pyproject.toml`, run `uv sync` to re-register entry points.

---

## 3. Command Migration Table

| Command | Current CLI | Target CLI | Signature Changes | Notes |
|---------|-------------|------------|-------------------|-------|
| `init` | `lexi` | `lexictl` | None | Help text on `--agent` flag: `"lexi setup"` → `"lexictl setup"` |
| `lookup <file>` | `lexi` | `lexi` | None | Cross-ref messages updated (see section 4) |
| `index <dir> [-r]` | `lexi` | `lexi` | None | No changes needed |
| `describe <dir> "desc"` | `lexi` | `lexi` | None | No changes needed |
| `concepts [topic]` | `lexi` | `lexi` | None | No changes needed |
| `concept new <name>` | `lexi` | `lexi` | None | No changes needed |
| `concept link <concept> <file>` | `lexi` | `lexi` | None | Cross-ref message updated |
| `stack post/search/answer/vote/accept/view/list` | `lexi` | `lexi` | None | No changes needed |
| `search` | `lexi` | `lexi` | None | No changes needed |
| `update [path]` | `lexi` | `lexictl` | None | Becomes `lexictl update` |
| `validate [--severity] [--check] [--json]` | `lexi` | `lexictl` | None | Becomes `lexictl validate` |
| `status [--quiet]` | `lexi` | `lexictl` | None | Cross-ref messages updated |
| `setup [env] [--update]` | `lexi` | `lexictl` | None | Still a stub |
| `daemon [path]` | `lexi` | `lexictl` | None | Still a stub |

---

## 4. Cross-Reference Updates

Every place in the codebase where a command name is referenced in help text, error messages, or suggestions must be updated to reference the correct CLI.

### 4a. Source Code Changes in `cli/` (formerly `cli.py`)

| Location (current line) | Current Text | New Text | Which App File |
|---|---|---|---|
| Line 45 (`_require_project_root`) | `Run [cyan]lexi init[/cyan]` | `Run [cyan]lexictl init[/cyan]` | `_shared.py` |
| Line 68 (init `--agent` help) | `Handled by \`lexi setup\`` | `Handled by \`lexictl setup\`` | `lexictl_app.py` |
| Line 83 (init `--agent` output) | `Run [cyan]lexi setup {agent}[/cyan]` | `Run [cyan]lexictl setup {agent}[/cyan]` | `lexictl_app.py` |
| Line 127 (lookup, no design file) | `Run [cyan]lexi update {file}[/cyan]` | `Run [cyan]lexictl update {file}[/cyan]` | `lexi_app.py` |
| Line 140 (lookup, stale design file) | `Run [cyan]lexi update ...` | `Run [cyan]lexictl update ...` | `lexi_app.py` |
| Line 386 (concept_link, no design file) | `Run [cyan]lexi update {source_file}[/cyan]` | `Run [cyan]lexictl update {source_file}[/cyan]` | `lexi_app.py` |
| Line 1224 (status, quiet with errors+warnings) | `run \`lexi validate\`` | `run \`lexictl validate\`` | `lexictl_app.py` |
| Line 1229 (status, quiet with errors only) | `run \`lexi validate\`` | `run \`lexictl validate\`` | `lexictl_app.py` |
| Line 1234 (status, quiet with warnings only) | `run \`lexi validate\`` | `run \`lexictl validate\`` | `lexictl_app.py` |
| Line 1311 (status, full dashboard) | `Run \`lexi validate\` for details.` | `Run \`lexictl validate\` for details.` | `lexictl_app.py` |

### 4b. Source Code Changes Outside `cli/`

| File | Current Text | New Text |
|---|---|---|
| `src/lexibrary/validator/checks.py` line 366 | `suggestion="Run \`lexi update\`..."` | `suggestion="Run \`lexictl update\`..."` |
| `src/lexibrary/init/scaffolder.py` line 23 | `Run \`lexi update\` to crawl the project` | `Run \`lexictl update\` to crawl the project` |
| `src/lexibrary/config/defaults.py` line 7 | `# This file is created by \`lexi init\`` | `# This file is created by \`lexictl init\`` |
| `src/lexibrary/daemon/service.py` line 49 | `Use [cyan]lexi daemon --foreground[/cyan]` | `Use [cyan]lexictl daemon --foreground[/cyan]` |

Note: `checks.py` line 838 suggests `"Run 'lexi index' to generate .aindex files"` — `lexi index` stays on `lexi`, so this is correct and needs no change.

### 4c. Status `--quiet` Prefix String

The current `status` command outputs lines prefixed with `"lexi: "` in quiet mode. Since `status` moves to `lexictl`:

```python
# Before
console.print("lexi: library healthy")
console.print("lexi: " + ", ".join(parts) + " — run `lexi validate`")

# After
console.print("lexictl: library healthy")
console.print("lexictl: " + ", ".join(parts) + " — run `lexictl validate`")
```

---

## 5. Import Structure

### Shared Imports

Both apps import from `_shared.py`:

```python
from lexibrary.cli._shared import console, require_project_root, stub
```

### Lazy Imports Preserved

The current `cli.py` uses lazy imports inside command functions to keep CLI startup fast. This pattern is preserved exactly. Each command function continues to import its dependencies at invocation time, not at module level.

### Module-Level Imports by File

**`_shared.py`** (eager, unavoidable):
- `typer`, `rich.console.Console`, `pathlib.Path`
- `lexibrary.exceptions.LexibraryNotFoundError`
- `lexibrary.utils.root.find_project_root`

**`lexi_app.py`** (eager):
- `typer`, `pathlib.Path`, `typing.Annotated`
- `lexibrary.cli._shared` (console, require_project_root)

**`lexictl_app.py`** (eager):
- `typer`, `pathlib.Path`, `typing.Annotated`, `asyncio`, `hashlib`
- `lexibrary.cli._shared` (console, require_project_root, stub)
- `lexibrary.init.scaffolder.create_lexibrary_skeleton`

---

## 6. Test Strategy

### Current State

All CLI tests live in `tests/test_cli.py`. They import `from lexibrary.cli import app` and use a single `CliRunner` instance.

### Plan: Split into Two Test Files

Create a `tests/test_cli/` package:

```
tests/test_cli/
    __init__.py
    test_lexi.py       # Tests for agent-facing commands
    test_lexictl.py     # Tests for maintenance commands
```

**`test_lexi.py`** imports and tests `lexi_app`:
```python
from lexibrary.cli import lexi_app
runner = CliRunner()
```

Test classes that move here:
- `TestHelp` -- rewritten to check `lexi_app` help (only agent-facing commands listed)
- `TestIndexCommand`, `TestLookupCommand`, `TestLookupConventionInheritance`
- `TestDescribeCommand`, `TestConceptsCommand`, `TestConceptNewCommand`, `TestConceptLinkCommand`
- All `TestStack*Command` classes
- `TestUnifiedSearchCommand`

**`test_lexictl.py`** imports and tests `lexictl_app`:
```python
from lexibrary.cli import lexictl_app
runner = CliRunner()
```

Test classes that move here:
- `TestHelp` -- new test checking `lexictl_app` help
- `TestInit`, `TestUpdateCommand`, `TestValidateCommand`, `TestStatusCommand`
- `TestStubCommands` -- narrowed to only `setup` and `daemon` stubs

**`TestNoProjectRoot`** is split across both files.

### Specific Test Assertion Changes

| Test Class | Current Assertion | New Assertion |
|---|---|---|
| `TestInit` | `assert "lexi setup claude" in result.output` | `assert "lexictl setup claude" in result.output` |
| `TestNoProjectRoot` | `assert "lexi init" in result.output` | `assert "lexictl init" in result.output` |
| `TestLookupCommand` | `assert "lexi update" in result.output` | `assert "lexictl update" in result.output` |
| `TestConceptLinkCommand` | `assert "lexi update" in result.output` | `assert "lexictl update" in result.output` |
| `TestStatusCommand` | `assert "lexi validate" in output` | `assert "lexictl validate" in output` |
| `TestHelp::test_help_lists_all_commands` | Checks for all commands in single app | Split: `test_lexi.py` checks for `lookup`, `index`, etc.; `test_lexictl.py` checks for `init`, `update`, etc. |

### Test for Validator Suggestion Text

Update `tests/test_validator/test_warning_checks.py`:
```python
# "lexi update" → "lexictl update"
```

Update `tests/test_validator/test_report.py`:
```python
# "Run lexi update" → "Run lexictl update"
```

---

## 7. Implementation Sequence

All steps are within a single logical change (one PR). Order keeps tests passing at each step.

### Step 1: Create the `cli/` Package Structure

1. Create directory `src/lexibrary/cli/`
2. Create `src/lexibrary/cli/__init__.py` with re-exports
3. Create `src/lexibrary/cli/_shared.py` with shared helpers
4. Create `src/lexibrary/cli/lexi_app.py` with agent-facing commands
5. Create `src/lexibrary/cli/lexictl_app.py` with maintenance commands
6. Delete `src/lexibrary/cli.py`

### Step 2: Update Cross-References in Source Code

1. Update `_shared.py` message: `lexi init` → `lexictl init`
2. Update `lexictl_app.py` `init` command: `lexi setup` → `lexictl setup`
3. Update `lexi_app.py` `lookup` command: `lexi update` → `lexictl update` (two places)
4. Update `lexi_app.py` `concept_link` command: `lexi update` → `lexictl update`
5. Update `lexictl_app.py` `status` command: `lexi validate` → `lexictl validate` (four places)
6. Update `lexictl_app.py` `status` quiet prefix: `lexi:` → `lexictl:`
7. Update `src/lexibrary/validator/checks.py`: `lexi update` → `lexictl update`
8. Update `src/lexibrary/init/scaffolder.py`: `lexi update` → `lexictl update`
9. Update `src/lexibrary/config/defaults.py`: `lexi init` → `lexictl init`
10. Update `src/lexibrary/daemon/service.py`: `lexi daemon` → `lexictl daemon`

### Step 3: Update Entry Points

1. Update `pyproject.toml` `[project.scripts]`:
   ```toml
   lexi = "lexibrary.cli:lexi_app"
   lexictl = "lexibrary.cli:lexictl_app"
   ```
2. Update `src/lexibrary/__main__.py` to import `lexi_app`
3. Run `uv sync` to re-register entry points

### Step 4: Update Tests

1. Create `tests/test_cli/` directory with `__init__.py`
2. Create `tests/test_cli/test_lexi.py` with agent-facing command tests
3. Create `tests/test_cli/test_lexictl.py` with maintenance command tests
4. Update all assertion strings referencing moved commands
5. Delete `tests/test_cli.py`
6. Update `tests/test_validator/test_warning_checks.py`
7. Update `tests/test_validator/test_report.py`

### Step 5: Update Blueprints

1. Update `blueprints/START_HERE.md` to reflect `cli/` package structure
2. Replace `blueprints/src/lexibrary/cli.md` with package-level design files:
   - `blueprints/src/lexibrary/cli/__init__.md`
   - `blueprints/src/lexibrary/cli/_shared.md`
   - `blueprints/src/lexibrary/cli/lexi_app.md`
   - `blueprints/src/lexibrary/cli/lexictl_app.md`

### Step 6: Verify

1. `uv run pytest --cov=lexibrary` -- all tests pass
2. `uv run ruff check src/ tests/` -- no lint issues
3. `uv run ruff format src/ tests/` -- formatting clean
4. `uv run mypy src/` -- type checks pass
5. Manual smoke test: `uv run lexi --help` shows only agent commands
6. Manual smoke test: `uv run lexictl --help` shows only maintenance commands
7. Verify `lexi update` does NOT exist
8. Verify `lexictl lookup` does NOT exist

---

## 8. Risks and Edge Cases

### 8.1 Import Path Change for `app`

The current import `from lexibrary.cli import app` is used in tests and `__main__.py`. After the change, `app` no longer exists — `__init__.py` exports `lexi_app` and `lexictl_app`. No backwards-compatible alias needed (pre-1.0).

### 8.2 Stack Helpers are `lexi`-Only

`_stack_dir()`, `_next_stack_id()`, `_slugify()`, and `_find_post_path()` are used exclusively by stack commands. They move to `lexi_app.py` as private functions. They do not belong in `_shared.py`.

### 8.3 The `concept_app` and `stack_app` Sub-Groups

Both are Typer sub-apps. Their registrations move to `lexi_app.py`:

```python
concept_app = typer.Typer(help="Concept management commands.")
app.add_typer(concept_app, name="concept")

stack_app = typer.Typer(help="Stack Q&A management commands.")
app.add_typer(stack_app, name="stack")
```

### 8.4 `lexi init` No Longer Exists

After the split, running `lexi init` produces a Typer "No such command" error. This is intended per D-052 and D-054. The `require_project_root()` error message directs users to `lexictl init`.

### 8.5 Test Runner Discovery

Moving from `tests/test_cli.py` to `tests/test_cli/test_lexi.py` and `tests/test_cli/test_lexictl.py` requires an `__init__.py` in `tests/test_cli/`. Pytest with `testpaths = ["tests"]` discovers the new location automatically.

### 8.6 `from __future__ import annotations`

Every new module must include this import at the top.

---

## 9. Summary of All Files Changed

### New Files Created
| File | Purpose |
|---|---|
| `src/lexibrary/cli/__init__.py` | Package init, re-exports `lexi_app` and `lexictl_app` |
| `src/lexibrary/cli/_shared.py` | Shared helpers: `console`, `require_project_root()`, `stub()` |
| `src/lexibrary/cli/lexi_app.py` | Agent-facing Typer app + commands |
| `src/lexibrary/cli/lexictl_app.py` | Maintenance Typer app + commands |
| `tests/test_cli/__init__.py` | Test package init |
| `tests/test_cli/test_lexi.py` | Tests for `lexi` commands |
| `tests/test_cli/test_lexictl.py` | Tests for `lexictl` commands |

### Files Deleted
| File | Reason |
|---|---|
| `src/lexibrary/cli.py` | Replaced by `cli/` package |
| `tests/test_cli.py` | Replaced by `tests/test_cli/` package |

### Files Modified
| File | Change |
|---|---|
| `pyproject.toml` | Entry points: `lexi` and `lexictl`, drop `lexibrary` alias |
| `src/lexibrary/__main__.py` | Import `lexi_app` instead of `app` |
| `src/lexibrary/validator/checks.py` | `"lexi update"` → `"lexictl update"` in suggestion string |
| `src/lexibrary/init/scaffolder.py` | `"lexi update"` → `"lexictl update"` in START_HERE placeholder |
| `src/lexibrary/config/defaults.py` | `"lexi init"` → `"lexictl init"` in config comment |
| `src/lexibrary/daemon/service.py` | `"lexi daemon"` → `"lexictl daemon"` in error message |
| `tests/test_validator/test_warning_checks.py` | `"lexi update"` → `"lexictl update"` in assertion |
| `tests/test_validator/test_report.py` | `"lexi update"` → `"lexictl update"` in test data |
| `blueprints/START_HERE.md` | Update topology tree and references |
| `blueprints/src/lexibrary/cli.md` | Replace with package-level design files |
