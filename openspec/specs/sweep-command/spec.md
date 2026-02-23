# sweep-command Specification

## Purpose
TBD - created by archiving change update-triggers. Update Purpose after archive.
## Requirements
### Requirement: lexictl sweep command
The system SHALL provide a `lexictl sweep` command for running library update sweeps.

#### Scenario: One-shot sweep
- **WHEN** `lexictl sweep` is run without flags
- **THEN** a single update sweep SHALL be performed and the command SHALL exit
- **AND** the sweep SHALL use `DaemonService.run_once()`

#### Scenario: Watch mode
- **WHEN** `lexictl sweep --watch` is run
- **THEN** periodic sweeps SHALL run in the foreground at the configured interval
- **AND** the command SHALL block until interrupted (Ctrl+C)
- **AND** the sweep SHALL use `DaemonService.run_watch()`

#### Scenario: Requires project root
- **WHEN** `lexictl sweep` is run outside a Lexibrary project (no `.lexibrary/` directory)
- **THEN** the command SHALL exit with an error via `require_project_root()`

