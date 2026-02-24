## ADDED Requirements

### Requirement: lexi validate command
The `lexi validate` command SHALL run all validation checks via `validate_library()` and display results using Rich rendering. It SHALL accept the same flags as `lexictl validate`: `--severity`, `--check`, and `--json`. It SHALL use exit codes 0 (clean), 1 (errors), 2 (warnings only).

#### Scenario: lexi validate runs all checks
- **WHEN** running `lexi validate` on a library with broken wikilinks
- **THEN** the output SHALL show errors grouped under "Errors" and exit code SHALL be 1

#### Scenario: lexi validate with severity filter
- **WHEN** running `lexi validate --severity warning`
- **THEN** only error and warning issues SHALL be displayed; info issues SHALL be excluded

#### Scenario: lexi validate with check filter
- **WHEN** running `lexi validate --check hash_freshness`
- **THEN** only the hash freshness check SHALL run and its results SHALL be displayed

#### Scenario: lexi validate with JSON output
- **WHEN** running `lexi validate --json`
- **THEN** stdout SHALL contain valid JSON with "issues" and "summary" keys

#### Scenario: lexi validate requires project root
- **WHEN** running `lexi validate` outside a Lexibrary project
- **THEN** the command SHALL print an error referencing `lexictl init` and exit with non-zero code

### Requirement: lexi status command
The `lexi status` command SHALL display library health including design file counts, concept counts by status, Stack post counts, link graph health, issue counts, and last update timestamp. It SHALL accept a `--quiet` flag for single-line CI/hook output. It SHALL use exit codes 0 (clean), 1 (errors), 2 (warnings only).

#### Scenario: lexi status shows full dashboard
- **WHEN** running `lexi status` on a library with 47 design files (3 stale)
- **THEN** the output SHALL include "Files: 47 tracked, 3 stale" and other dashboard sections

#### Scenario: lexi status quiet mode with prefix
- **WHEN** running `lexi status --quiet` with 3 warnings and 0 errors
- **THEN** output SHALL be exactly `lexi: 3 warnings — run \`lexi validate\``

#### Scenario: lexi status quiet mode when healthy
- **WHEN** running `lexi status --quiet` with no errors or warnings
- **THEN** output SHALL be exactly `lexi: library healthy`

#### Scenario: lexi status suggests lexi validate
- **WHEN** running `lexi status` and the library has warnings
- **THEN** the output SHALL end with `Run \`lexi validate\` for details.`

#### Scenario: lexi status requires project root
- **WHEN** running `lexi status` outside a Lexibrary project
- **THEN** the command SHALL print an error referencing `lexictl init` and exit with non-zero code

### Requirement: lexictl index command
The `lexictl index` command SHALL accept a `directory` argument (default `.`) and a `-r`/`--recursive` boolean flag (default `False`). It SHALL require an initialized `.lexibrary/` directory and generate `.aindex` files via the indexer module. The interface SHALL be identical to the former `lexi index` command.

#### Scenario: lexictl index single directory
- **WHEN** running `lexictl index src/` in a project with `.lexibrary/`
- **THEN** a `.aindex` file SHALL be written at `.lexibrary/src/.aindex` and the command SHALL exit with code 0

#### Scenario: lexictl index recursive
- **WHEN** running `lexictl index -r .`
- **THEN** `.aindex` files SHALL be written for all directories in the project tree bottom-up

#### Scenario: lexictl index fails without project
- **WHEN** running `lexictl index src/` without `.lexibrary/`
- **THEN** the command SHALL print an error referencing `lexictl init` and exit with non-zero code

#### Scenario: lexictl index displays summary
- **WHEN** `lexictl index` completes
- **THEN** the output SHALL include a count of directories indexed and files found

### Requirement: lexi help content reflects rebalanced commands
The `lexi help` command output SHALL organize commands into sections that reflect the rebalanced CLI. The "Indexing & Maintenance" section SHALL be replaced by an "Inspection & Annotation" section containing `lexi status`, `lexi validate`, and `lexi describe`. The "Index a new directory" workflow SHALL be replaced by a "Check library health" workflow using `lexi status` and `lexi validate`.

#### Scenario: Help shows Inspection & Annotation section
- **WHEN** running `lexi help`
- **THEN** the output SHALL contain a section titled "Inspection & Annotation" listing `lexi status`, `lexi validate`, and `lexi describe`

#### Scenario: Help does NOT show Indexing & Maintenance section
- **WHEN** running `lexi help`
- **THEN** the output SHALL NOT contain a section titled "Indexing & Maintenance"

#### Scenario: Help does NOT reference lexi index
- **WHEN** running `lexi help`
- **THEN** the output SHALL NOT contain `lexi index`

#### Scenario: Help shows Check library health workflow
- **WHEN** running `lexi help`
- **THEN** the "Common Workflows" panel SHALL include a workflow titled "Check library health" that references `lexi status` and `lexi validate`

## MODIFIED Requirements

### Requirement: lexi help lists only agent commands
The `lexi --help` output SHALL list only agent-facing commands: `lookup`, `describe`, `concepts`, `concept`, `stack`, `search`, `validate`, `status`, `help`. It SHALL NOT list `index`.

#### Scenario: lexi help shows agent commands
- **WHEN** running `lexi --help`
- **THEN** the output SHALL list `lookup`, `describe`, `concepts`, `concept`, `stack`, `search`, `validate`, `status`, `help`

#### Scenario: lexi help does NOT show maintenance commands
- **WHEN** running `lexi --help`
- **THEN** the output SHALL NOT contain `init`, `update`, `index`, `setup`, `sweep`, or `daemon`
