## MODIFIED Requirements

### Requirement: CLI application structure
The system SHALL provide a Typer application with help text and a `no_args_is_help=True` setting so that running the command without arguments displays help.

#### Scenario: CLI app is accessible
- **WHEN** importing `from lexibrary.cli import app`
- **THEN** app is a Typer instance with name "lexibrary"

#### Scenario: Help is displayed when no arguments given
- **WHEN** running `lexi` or `lexibrary` with no arguments
- **THEN** the help text is displayed (not an error)

#### Scenario: Application has descriptive help text
- **WHEN** running `lexi --help`
- **THEN** the help text includes "AI-friendly codebase indexer" and mentions the `.lexibrary/` library

### Requirement: Init command
The system SHALL provide an `init` command that accepts an optional `--agent` option (`cursor`, `claude`, `codex`) and creates the `.lexibrary/` directory skeleton in the current working directory.

#### Scenario: Init command creates .lexibrary/ skeleton
- **WHEN** running `lexi init` in an empty directory
- **THEN** `.lexibrary/`, `.lexibrary/config.yaml`, `.lexibrary/START_HERE.md`, `.lexibrary/HANDOFF.md`, `.lexibrary/concepts/`, and `.lexibrary/guardrails/` are created

#### Scenario: Init command accepts --agent flag
- **WHEN** running `lexi init --agent claude`
- **THEN** the command runs without error; the `--agent` value is accepted and a note is printed that `lexi setup` handles agent environment configuration

#### Scenario: Init is idempotent
- **WHEN** running `lexi init` in a project that already has `.lexibrary/`
- **THEN** the command succeeds, prints a notice that `.lexibrary/` already exists, and does not overwrite existing files

#### Scenario: Init command has help text
- **WHEN** running `lexi init --help`
- **THEN** the help text describes "Initialize Lexibrary in a project. Creates .lexibrary/ directory."

### Requirement: Daemon command
The system SHALL provide a `daemon` command that accepts a path argument (default ".") and prints a "not yet implemented" stub message via `rich.console.Console`. Full implementation comes in Phase 9.

#### Scenario: Daemon command accepts path argument
- **WHEN** running `lexi daemon /some/path`
- **THEN** the command executes without error and prints a stub message

#### Scenario: Daemon command defaults to current directory
- **WHEN** running `lexi daemon` with no path argument
- **THEN** the command executes with path="."

#### Scenario: Daemon command has help text
- **WHEN** running `lexi daemon --help`
- **THEN** the help text says "Start the background file watcher daemon."

### Requirement: Status command
The system SHALL provide a `status` command that accepts a path argument (default ".") and prints a "not yet implemented" stub message via `rich.console.Console`. Full implementation comes in Phase 7.

#### Scenario: Status command accepts path argument
- **WHEN** running `lexi status /some/path`
- **THEN** the command executes without error and prints a stub message

#### Scenario: Status command defaults to current directory
- **WHEN** running `lexi status` with no path argument
- **THEN** the command executes with path="."

#### Scenario: Status command has help text
- **WHEN** running `lexi status --help`
- **THEN** the help text says "Show library health and staleness summary."

### Requirement: Command aliases
The system SHALL support both `lexi` and `lexibrary` as command entry points that execute the same application.

#### Scenario: Both command names work
- **WHEN** running `lexi --help` and `lexibrary --help`
- **THEN** both produce identical output listing all registered commands

## REMOVED Requirements

### Requirement: Crawl command
**Reason**: The `crawl` command is retired in v2. Its functionality is replaced by `lexi update` (Phase 4) and `lexi index` (Phase 2).
**Migration**: Remove `crawl` from CLI. Users should use `lexi update [<path>]` instead.

### Requirement: Clean command
**Reason**: The `clean` command that removed `.aindex` files is no longer applicable. The v2 library lives in `.lexibrary/` which is managed differently.
**Migration**: Remove `clean` from CLI. Library cleanup will be addressed in a future phase if needed.

## ADDED Requirements

### Requirement: Stub command behavior
All commands that are not implemented in Phase 1 SHALL print a yellow "Not yet implemented." message via `rich.console.Console` and exit with code 0 (not an error). This ensures `lexi --help` shows the full v2 command surface from Phase 1 onward.

#### Scenario: Unimplemented command prints stub message
- **WHEN** running any stub command (e.g., `lexi lookup somefile.py`)
- **THEN** the output contains "Not yet implemented" (case-insensitive) and the exit code is 0

#### Scenario: Stub commands do not raise exceptions
- **WHEN** running any stub command
- **THEN** no Python exception is raised (only a clean exit)

### Requirement: Lookup command stub
The system SHALL provide a `lookup` command that accepts a file path argument and prints a stub message. Full implementation in Phase 4.

#### Scenario: Lookup command has correct help text
- **WHEN** running `lexi lookup --help`
- **THEN** the help text describes "Return the design file for a source file."

### Requirement: Index command stub
The system SHALL provide an `index` command that accepts a directory path argument and prints a stub message. Full implementation in Phase 2.

#### Scenario: Index command has correct help text
- **WHEN** running `lexi index --help`
- **THEN** the help text describes "Return or generate the .aindex for a directory."

### Requirement: Concepts command stub
The system SHALL provide a `concepts` command that accepts an optional topic argument and prints a stub message. Full implementation in Phase 5.

#### Scenario: Concepts command has correct help text
- **WHEN** running `lexi concepts --help`
- **THEN** the help text describes "List or search concept files."

### Requirement: Guardrails command stub
The system SHALL provide a `guardrails` command that accepts optional `--scope` and `--concept` options and prints a stub message. Full implementation in Phase 6.

#### Scenario: Guardrails command has correct help text
- **WHEN** running `lexi guardrails --help`
- **THEN** the help text describes "Search guardrail threads."

### Requirement: Guardrail new subcommand stub
The system SHALL provide a `guardrail new` subcommand that accepts `--file`, `--mistake`, and `--resolution` options and prints a stub message. Full implementation in Phase 6.

#### Scenario: Guardrail new command has correct help text
- **WHEN** running `lexi guardrail new --help`
- **THEN** the help text describes "Record a new guardrail thread."

### Requirement: Search command stub
The system SHALL provide a `search` command that accepts a `--tag` option and an optional `--scope` option and prints a stub message. Full implementation in Phase 7.

#### Scenario: Search command has correct help text
- **WHEN** running `lexi search --help`
- **THEN** the help text describes "Search artifacts by tag across the library."

### Requirement: Update command stub
The system SHALL provide an `update` command that accepts an optional path argument and prints a stub message. Full implementation in Phase 4.

#### Scenario: Update command has correct help text
- **WHEN** running `lexi update --help`
- **THEN** the help text describes "Re-index changed files and regenerate design files."

### Requirement: Validate command stub
The system SHALL provide a `validate` command that prints a stub message. Full implementation in Phase 7.

#### Scenario: Validate command has correct help text
- **WHEN** running `lexi validate --help`
- **THEN** the help text describes "Run consistency checks on the library."

### Requirement: Setup command stub
The system SHALL provide a `setup` command that accepts an environment argument (`cursor`, `claude`, `codex`) and an optional `--update` flag, and prints a stub message. Full implementation in Phase 8.

#### Scenario: Setup command has correct help text
- **WHEN** running `lexi setup --help`
- **THEN** the help text describes "Install or update agent environment rules."
