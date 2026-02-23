## ADDED Requirements

### Requirement: Test directory structure
CLI tests SHALL be organized as a package at `tests/test_cli/` containing `__init__.py`, `test_lexi.py` (agent-facing command tests), and `test_lexictl.py` (maintenance command tests). The monolithic `tests/test_cli.py` file SHALL NOT exist.

#### Scenario: Test CLI package exists
- **WHEN** inspecting `tests/test_cli/`
- **THEN** it is a directory containing `__init__.py`, `test_lexi.py`, and `test_lexictl.py`

#### Scenario: Old test file does not exist
- **WHEN** inspecting `tests/`
- **THEN** there is no `test_cli.py` file

## MODIFIED Requirements

### Requirement: Project directory structure
The system SHALL have a Python package structure with source code under `src/lexibrary/` and test code under `tests/`. The CLI SHALL be a package at `src/lexibrary/cli/` (not a single file).

#### Scenario: CLI is a package directory
- **WHEN** inspecting `src/lexibrary/cli/`
- **THEN** it is a directory containing `__init__.py`, `_shared.py`, `lexi_app.py`, and `lexictl_app.py`

#### Scenario: No cli.py file exists
- **WHEN** inspecting `src/lexibrary/`
- **THEN** there is no `cli.py` file

### Requirement: Project metadata in pyproject.toml
The `[project.scripts]` section SHALL define two entry points: `lexi` mapping to `"lexibrary.cli:lexi_app"` and `lexictl` mapping to `"lexibrary.cli:lexictl_app"`. The `lexibrary` alias SHALL NOT exist.

#### Scenario: CLI entry points are configured
- **WHEN** reading `pyproject.toml` `[project.scripts]`
- **THEN** `lexi` maps to `"lexibrary.cli:lexi_app"` and `lexictl` maps to `"lexibrary.cli:lexictl_app"`

#### Scenario: No lexibrary alias exists
- **WHEN** reading `pyproject.toml` `[project.scripts]`
- **THEN** there is no `lexibrary` entry

### Requirement: Module initialization
The `__main__.py` SHALL import and run `lexi_app` (the agent-facing CLI) when invoked via `python -m lexibrary`.

#### Scenario: Root module can be run as a script
- **WHEN** running `python -m lexibrary`
- **THEN** it runs the `lexi_app` (agent-facing CLI)

### Requirement: Stack directory in scaffolding
`lexictl init` SHALL create a `.lexibrary/stack/` directory in the project skeleton.

#### Scenario: Init creates stack directory
- **WHEN** running `lexictl init` in an empty directory
- **THEN** `.lexibrary/stack/` SHALL be created
