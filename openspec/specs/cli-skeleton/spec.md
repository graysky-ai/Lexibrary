# cli-skeleton Specification

## Purpose
TBD - created by archiving change phase-1-foundation. Update Purpose after archive.
## Requirements
### Requirement: CLI application structure
The system SHALL provide two Typer applications: `lexi_app` (agent-facing, name "lexi") and `lexictl_app` (maintenance, name "lexictl"), both with help text and `no_args_is_help=True`. Running either command without arguments SHALL display its respective help.

#### Scenario: lexi app is accessible
- **WHEN** importing `from lexibrary.cli import lexi_app`
- **THEN** `lexi_app` is a Typer instance with name "lexi"

#### Scenario: lexictl app is accessible
- **WHEN** importing `from lexibrary.cli import lexictl_app`
- **THEN** `lexictl_app` is a Typer instance with name "lexictl"

#### Scenario: Help is displayed when no arguments given
- **WHEN** running `lexi` or `lexictl` with no arguments
- **THEN** the respective help text is displayed (not an error)

#### Scenario: lexi help text describes agent-facing CLI
- **WHEN** running `lexi --help`
- **THEN** the help text includes "Agent-facing CLI" and mentions lookups, search, concepts, and Stack Q&A

#### Scenario: lexictl help text describes maintenance CLI
- **WHEN** running `lexictl --help`
- **THEN** the help text includes "Maintenance CLI" and mentions setup, design file generation, and validation

### Requirement: Init command
The `lexictl` CLI SHALL provide an `init` command that accepts an optional `--agent` option (`cursor`, `claude`, `codex`) and creates the `.lexibrary/` directory skeleton in the current working directory.

#### Scenario: Init command creates .lexibrary/ skeleton
- **WHEN** running `lexictl init` in an empty directory
- **THEN** `.lexibrary/`, `.lexibrary/config.yaml`, `.lexibrary/START_HERE.md`, `.lexibrary/concepts/`, and `.lexibrary/stack/` are created

#### Scenario: Init command accepts --agent flag
- **WHEN** running `lexictl init --agent claude`
- **THEN** the command runs without error; the `--agent` value is accepted and a note is printed that `lexictl setup` handles agent environment configuration

#### Scenario: Init is idempotent
- **WHEN** running `lexictl init` in a project that already has `.lexibrary/`
- **THEN** the command succeeds, prints a notice that `.lexibrary/` already exists, and does not overwrite existing files

#### Scenario: Init command has help text
- **WHEN** running `lexictl init --help`
- **THEN** the help text describes "Initialize Lexibrary in a project. Creates .lexibrary/ directory."

### Requirement: Daemon command
The `lexictl` CLI SHALL provide a `daemon` command that accepts a path argument (default ".") and prints a "not yet implemented" stub message via `rich.console.Console`.

#### Scenario: Daemon command accepts path argument
- **WHEN** running `lexictl daemon /some/path`
- **THEN** the command executes without error and prints a stub message

#### Scenario: Daemon command defaults to current directory
- **WHEN** running `lexictl daemon` with no path argument
- **THEN** the command executes with path="."

#### Scenario: Daemon command has help text
- **WHEN** running `lexictl daemon --help`
- **THEN** the help text says "Start the background file watcher daemon."

### Requirement: Status command
The `lexictl` CLI SHALL provide a `status` command that displays library health and staleness summary.

#### Scenario: Status command accepts --quiet flag
- **WHEN** running `lexictl status --quiet`
- **THEN** the command outputs a compact one-line summary

#### Scenario: Status command has help text
- **WHEN** running `lexictl status --help`
- **THEN** the help text says "Show library health and staleness summary."

### Requirement: Stub command behavior
All commands on `lexictl` that are not yet implemented SHALL print a yellow "Not yet implemented." message via `rich.console.Console` and exit with code 0.

#### Scenario: Unimplemented lexictl command prints stub message
- **WHEN** running any stub command (e.g., `lexictl setup cursor`)
- **THEN** the output contains "Not yet implemented" (case-insensitive) and the exit code is 0

#### Scenario: Stub commands do not raise exceptions
- **WHEN** running any stub command on `lexictl`
- **THEN** no Python exception is raised (only a clean exit)

