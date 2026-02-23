## ADDED Requirements

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
- **THEN** the help text includes "AI-friendly codebase indexer" and mentions creating `.aindex` files

### Requirement: Init command
The system SHALL provide an `init` command that takes a path argument (default ".") and prints a placeholder message. Full implementation comes in a later phase.

#### Scenario: Init command accepts path argument
- **WHEN** running `lexi init /some/path`
- **THEN** the command executes without error and prints a placeholder message

#### Scenario: Init command defaults to current directory
- **WHEN** running `lexi init` with no path argument
- **THEN** the command executes with path="."

#### Scenario: Init command has help text
- **WHEN** running `lexi init --help`
- **THEN** the help text says "Initialize Lexibrary in a project. Creates lexibrary.toml."

### Requirement: Crawl command
The system SHALL provide a `crawl` command that takes a path argument (default ".") and prints a placeholder message. Full implementation comes in a later phase.

#### Scenario: Crawl command accepts path argument
- **WHEN** running `lexi crawl /some/path`
- **THEN** the command executes without error and prints a placeholder message

#### Scenario: Crawl command defaults to current directory
- **WHEN** running `lexi crawl` with no path argument
- **THEN** the command executes with path="."

#### Scenario: Crawl command has help text
- **WHEN** running `lexi crawl --help`
- **THEN** the help text says "Run the Lexibrary crawler."

### Requirement: Daemon command
The system SHALL provide a `daemon` command that takes a path argument (default ".") and prints a placeholder message. Full implementation comes in a later phase.

#### Scenario: Daemon command accepts path argument
- **WHEN** running `lexi daemon /some/path`
- **THEN** the command executes without error and prints a placeholder message

#### Scenario: Daemon command defaults to current directory
- **WHEN** running `lexi daemon` with no path argument
- **THEN** the command executes with path="."

#### Scenario: Daemon command has help text
- **WHEN** running `lexi daemon --help`
- **THEN** the help text says "Start the background daemon."

### Requirement: Status command
The system SHALL provide a `status` command that takes a path argument (default ".") and prints a placeholder message. Full implementation comes in a later phase.

#### Scenario: Status command accepts path argument
- **WHEN** running `lexi status /some/path`
- **THEN** the command executes without error and prints a placeholder message

#### Scenario: Status command defaults to current directory
- **WHEN** running `lexi status` with no path argument
- **THEN** the command executes with path="."

#### Scenario: Status command has help text
- **WHEN** running `lexi status --help`
- **THEN** the help text says "Show indexing status."

### Requirement: Clean command
The system SHALL provide a `clean` command that takes a path argument (default ".") and prints a placeholder message. Full implementation comes in a later phase.

#### Scenario: Clean command accepts path argument
- **WHEN** running `lexi clean /some/path`
- **THEN** the command executes without error and prints a placeholder message

#### Scenario: Clean command defaults to current directory
- **WHEN** running `lexi clean` with no path argument
- **THEN** the command executes with path="."

#### Scenario: Clean command has help text
- **WHEN** running `lexi clean --help`
- **THEN** the help text says "Remove all .aindex files and cache."

### Requirement: Command aliases
The system SHALL support both `lexi` and `lexibrary` as command entry points that execute the same application.

#### Scenario: Both command names work
- **WHEN** running `lexi --help` and `lexibrary --help`
- **THEN** both produce identical output listing all 5 commands
