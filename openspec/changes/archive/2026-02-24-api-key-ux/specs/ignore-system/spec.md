## MODIFIED Requirements

### Requirement: Config pattern matching
The system SHALL create a PathSpec from config-defined ignore patterns. The default `additional_patterns` list SHALL NOT include `.lexibrary/HANDOFF.md` (removed — HANDOFF.md replaced by IWH). The default `additional_patterns` SHALL include `.env`, `.env.*`, and `*.env` patterns so that environment files containing credentials are never crawled or sent to the Archivist as source content.

#### Scenario: Config patterns are compiled into a PathSpec
- **WHEN** creating a PathSpec from config.ignore.additional_patterns
- **THEN** it successfully matches relative paths against those patterns

#### Scenario: Default patterns do not include HANDOFF.md
- **WHEN** inspecting the default `IgnoreConfig.additional_patterns`
- **THEN** the list SHALL NOT contain `.lexibrary/HANDOFF.md`

#### Scenario: Default patterns include .env files
- **WHEN** inspecting the default `IgnoreConfig.additional_patterns`
- **THEN** the list SHALL contain `.env`, `.env.*`, and `*.env`

#### Scenario: .env file is ignored by default
- **WHEN** testing the path `.env` against the default config patterns
- **THEN** `is_ignored(".env")` SHALL return `True`

#### Scenario: .env.local is ignored by default
- **WHEN** testing the path `.env.local` against the default config patterns
- **THEN** `is_ignored(".env.local")` SHALL return `True`

#### Scenario: Config patterns match common files and directories
- **WHEN** testing paths like ".aindex", "node_modules/foo", "file.lock" against config patterns
- **THEN** they are correctly identified as matching

## ADDED Requirements

### Requirement: Scaffolder writes .env patterns to .lexignore
The `create_lexibrary_skeleton()` scaffolder SHALL include `.env`, `.env.*`, and `*.env` in the patterns written to the project's `.lexignore` file during `lexictl init`.

#### Scenario: .lexignore contains .env patterns after init
- **WHEN** `lexictl init` completes on a fresh project
- **THEN** the `.lexignore` file at the project root SHALL contain `.env`, `.env.*`, and `*.env` entries

#### Scenario: .lexignore .env patterns are idempotent
- **WHEN** `lexictl init` is run on a project that already has `.env` in `.lexignore`
- **THEN** duplicate entries SHALL NOT be added
