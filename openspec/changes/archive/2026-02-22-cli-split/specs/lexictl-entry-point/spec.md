## ADDED Requirements

### Requirement: lexictl Typer app definition
The system SHALL provide a Typer application named `lexictl` in `lexictl_app.py` with help text describing it as the maintenance CLI for Lexibrary. It SHALL have `no_args_is_help=True`.

#### Scenario: lexictl app is accessible
- **WHEN** importing `from lexibrary.cli import lexictl_app`
- **THEN** `lexictl_app` is a Typer instance with name "lexictl"

#### Scenario: lexictl help is displayed with no arguments
- **WHEN** running `lexictl` with no arguments
- **THEN** the help text is displayed including "Maintenance CLI for Lexibrary"

### Requirement: lexictl registers maintenance commands
The `lexictl` app SHALL register the following commands: `init`, `update`, `validate`, `status`, `setup`, `daemon`. These commands SHALL have identical signatures and behavior to their former `lexi` counterparts.

#### Scenario: lexictl help lists all maintenance commands
- **WHEN** running `lexictl --help`
- **THEN** the output lists `init`, `update`, `validate`, `status`, `setup`, and `daemon`

#### Scenario: lexictl help does NOT list agent commands
- **WHEN** running `lexictl --help`
- **THEN** the output does NOT contain `lookup`, `index`, `describe`, `concepts`, `concept`, `stack`, or `search`

#### Scenario: lexictl init works
- **WHEN** running `lexictl init` in an empty directory
- **THEN** the `.lexibrary/` skeleton is created (same behavior as former `lexi init`)

#### Scenario: lexictl update works
- **WHEN** running `lexictl update` in an initialized project
- **THEN** design files are generated/refreshed (same behavior as former `lexi update`)

#### Scenario: lexictl validate works
- **WHEN** running `lexictl validate` in an initialized project
- **THEN** validation checks run and results are displayed (same behavior as former `lexi validate`)

#### Scenario: lexictl status works
- **WHEN** running `lexictl status` in an initialized project
- **THEN** the library health dashboard is displayed (same behavior as former `lexi status`)

### Requirement: lexictl entry point in pyproject.toml
The `pyproject.toml` `[project.scripts]` section SHALL define `lexictl = "lexibrary.cli:lexictl_app"`.

#### Scenario: lexictl is registered as a script entry point
- **WHEN** reading `pyproject.toml` `[project.scripts]`
- **THEN** `lexictl` maps to `"lexibrary.cli:lexictl_app"`

### Requirement: lexictl status quiet mode prefix
The `lexictl status --quiet` output lines SHALL be prefixed with `"lexictl: "` (not `"lexi: "`).

#### Scenario: Quiet mode uses lexictl prefix
- **WHEN** running `lexictl status --quiet` on a healthy library
- **THEN** the output contains `"lexictl: library healthy"`

#### Scenario: Quiet mode warning uses lexictl prefix
- **WHEN** running `lexictl status --quiet` on a library with warnings
- **THEN** the output contains `"lexictl: "` followed by the warning summary and `"lexictl validate"`
