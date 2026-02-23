## ADDED Requirements

### Requirement: CLI package structure
The CLI SHALL be organized as a Python package at `src/lexibrary/cli/` containing `__init__.py`, `_shared.py`, `lexi_app.py`, and `lexictl_app.py`. The `__init__.py` SHALL re-export `lexi_app` and `lexictl_app` as the two public entry points.

#### Scenario: CLI package is importable
- **WHEN** importing `from lexibrary.cli import lexi_app, lexictl_app`
- **THEN** both imports succeed and each is a Typer instance

#### Scenario: CLI package directory exists
- **WHEN** inspecting `src/lexibrary/cli/`
- **THEN** it contains `__init__.py`, `_shared.py`, `lexi_app.py`, and `lexictl_app.py`

#### Scenario: Old cli.py no longer exists
- **WHEN** inspecting `src/lexibrary/`
- **THEN** there is no `cli.py` file (replaced by `cli/` package)

### Requirement: Shared helpers module
The `_shared.py` module SHALL export `console` (a `rich.console.Console` instance), `require_project_root()` (resolves project root or exits with error), and `stub()` (prints a standard stub message). Both `lexi_app.py` and `lexictl_app.py` SHALL import these from `_shared.py`.

#### Scenario: Shared console instance
- **WHEN** importing `from lexibrary.cli._shared import console`
- **THEN** `console` is a `rich.console.Console` instance

#### Scenario: require_project_root finds .lexibrary
- **WHEN** calling `require_project_root()` in a directory with `.lexibrary/`
- **THEN** it returns the project root `Path`

#### Scenario: require_project_root exits without .lexibrary
- **WHEN** calling `require_project_root()` in a directory with no `.lexibrary/`
- **THEN** it prints an error message containing "lexictl init" and raises `typer.Exit(1)`

#### Scenario: stub prints not-yet-implemented message
- **WHEN** calling `stub("setup")`
- **THEN** it prints a message containing "Not yet implemented" via the shared console

### Requirement: Shared helpers have no leading underscores
The shared helper functions SHALL be named `require_project_root` and `stub` (without leading underscores), since they are module-level exports in a shared module.

#### Scenario: Functions are public names
- **WHEN** importing from `lexibrary.cli._shared`
- **THEN** `require_project_root` and `stub` are available (not `_require_project_root` or `_stub`)

### Requirement: Lazy import pattern preserved
Each command function in `lexi_app.py` and `lexictl_app.py` SHALL continue to use lazy imports (importing dependencies inside the function body, not at module level) to keep CLI startup fast.

#### Scenario: Module-level imports are minimal
- **WHEN** inspecting the module-level imports of `lexi_app.py`
- **THEN** only `typer`, `pathlib.Path`, `typing.Annotated`, and `lexibrary.cli._shared` are imported at module level

#### Scenario: Command-specific imports are lazy
- **WHEN** inspecting any command function body (e.g., `lookup`, `index`)
- **THEN** domain-specific imports (e.g., `from lexibrary.archivist.pipeline import ...`) appear inside the function, not at module level

### Requirement: from __future__ import annotations in all modules
Every new module in the `cli/` package SHALL include `from __future__ import annotations` as the first import.

#### Scenario: All cli package modules have future annotations
- **WHEN** reading the first import line of `__init__.py`, `_shared.py`, `lexi_app.py`, and `lexictl_app.py`
- **THEN** each contains `from __future__ import annotations`
