## ADDED Requirements

### Requirement: Concept link suggests lexictl update
The `lexi concept link <concept> <file>` command SHALL suggest running `lexictl update <file>` (not `lexi update`) when the target file has no design file.

#### Scenario: Concept link missing design file suggestion
- **WHEN** running `lexi concept link Authentication src/auth.py` and no design file exists for `src/auth.py`
- **THEN** the output suggests running `lexictl update src/auth.py`

### Requirement: Cross-reference strings use correct CLI
All error messages, help text, and suggestions in CLI commands SHALL reference the correct CLI (`lexi` for agent commands, `lexictl` for maintenance commands). Specifically:
- `require_project_root()` error message SHALL reference `lexictl init`
- `init --agent` help text SHALL reference `lexictl setup`
- Lookup missing/stale design file messages SHALL reference `lexictl update`
- Status quiet mode output SHALL reference `lexictl validate`
- Status dashboard validation section SHALL reference `lexictl validate`

#### Scenario: Project root error references lexictl init
- **WHEN** any command that requires a project root is run outside a Lexibrary project
- **THEN** the error message contains "lexictl init" (not "lexi init")

#### Scenario: Init --agent help references lexictl setup
- **WHEN** running `lexictl init --agent claude`
- **THEN** the output contains "lexictl setup" (not "lexi setup")

#### Scenario: Lookup missing file references lexictl update
- **WHEN** running `lexi lookup` on a file with no design file
- **THEN** the suggestion contains "lexictl update" (not "lexi update")

### Requirement: lexi help lists only agent commands
The `lexi --help` output SHALL list only agent-facing commands: `lookup`, `index`, `describe`, `concepts`, `concept`, `stack`, `search`.

#### Scenario: lexi help shows agent commands
- **WHEN** running `lexi --help`
- **THEN** the output lists `lookup`, `index`, `describe`, `concepts`, `concept`, `stack`, `search`

#### Scenario: lexi help does NOT show maintenance commands
- **WHEN** running `lexi --help`
- **THEN** the output does NOT contain `init`, `update`, `validate`, `status`, `setup`, or `daemon`

## MODIFIED Requirements

### Requirement: Update command generates design files
`lexictl update [<path>]` SHALL generate or refresh design files for changed source files.
- If `path` is a file → update that single file's design file
- If `path` is a directory → update all files in that subtree within scope_root
- If no path → update all files in the project and regenerate START_HERE.md
- SHALL display a Rich progress bar for multi-file updates
- SHALL print summary stats on completion (including agent-updated count)
- SHALL exit with code 0 on success, 1 on any failures

#### Scenario: Update single file
- **WHEN** `lexictl update src/foo.py` is run
- **THEN** the system SHALL generate or refresh the design file at `.lexibrary/src/foo.py.md`

#### Scenario: Update directory
- **WHEN** `lexictl update src/` is run
- **THEN** the system SHALL update design files for all changed files under `src/` within scope_root

#### Scenario: Update entire project
- **WHEN** `lexictl update` is run with no arguments
- **THEN** the system SHALL update all changed files and regenerate START_HERE.md

#### Scenario: No project found
- **WHEN** `lexictl update` is run outside a Lexibrary project (no `.lexibrary/`)
- **THEN** the system SHALL print an error and exit with code 1

### Requirement: Lookup command returns design file
`lexi lookup <file>` SHALL return the design file content for a source file, followed by an `## Applicable Conventions` section listing inherited Local Conventions from parent `.aindex` files.
- SHALL check scope: if file is outside `scope_root`, print message and exit
- SHALL compute mirror path and read the design file
- If design file exists → print its content via Rich Console
- If design file doesn't exist → suggest running `lexictl update <file>`
- SHALL check staleness: if source_hash differs from current file hash, print warning before content
- SHALL walk from the file's parent directory up to `scope_root`, parsing each `.aindex` for `local_conventions`
- If any conventions are found → append an `## Applicable Conventions` section grouped by source directory
- If no conventions exist → no extra section appended

#### Scenario: Lookup existing design file
- **WHEN** `lexi lookup src/foo.py` is run and a design file exists
- **THEN** the design file content SHALL be printed

#### Scenario: Lookup missing design file
- **WHEN** `lexi lookup src/foo.py` is run and no design file exists
- **THEN** the system SHALL suggest running `lexictl update src/foo.py`

#### Scenario: Lookup shows staleness warning
- **WHEN** `lexi lookup src/foo.py` is run and the source file has changed since the design file was generated
- **THEN** a staleness warning SHALL be displayed before the content, suggesting `lexictl update`

#### Scenario: Lookup outside scope_root
- **WHEN** `lexi lookup scripts/deploy.sh` is run and `scripts/` is outside scope_root
- **THEN** the system SHALL print a message indicating the file is outside scope_root

#### Scenario: Lookup shows inherited conventions
- **WHEN** `lexi lookup src/payments/processor.py` is run and `src/payments/.aindex` and `src/.aindex` both have Local Conventions
- **THEN** the output includes an "## Applicable Conventions" section with conventions from both directories

#### Scenario: Lookup with no conventions
- **WHEN** `lexi lookup src/utils/helpers.py` is run and no parent `.aindex` files have Local Conventions
- **THEN** no extra conventions section is appended

### Requirement: Validate command runs library checks
The `lexictl validate` command SHALL run all validation checks via `validate_library()` and display the results using Rich rendering. It SHALL exit with code 0 (clean), 1 (errors found), or 2 (warnings only, no errors).

#### Scenario: Validate clean library exits 0
- **WHEN** running `lexictl validate` on a library with no issues
- **THEN** the output shows "Summary: 0 errors, 0 warnings, 0 info" and exit code is 0

#### Scenario: Validate with errors exits 1
- **WHEN** running `lexictl validate` on a library with broken wikilinks
- **THEN** the output shows the errors grouped under "Errors" and exit code is 1

#### Scenario: Validate with only warnings exits 2
- **WHEN** running `lexictl validate` on a library with stale design files but no broken references
- **THEN** the output shows warnings grouped under "Warnings" and exit code is 2

### Requirement: Validate supports severity filter
The `lexictl validate --severity <level>` option SHALL filter results to only show issues at or above the given severity level (error > warning > info).

#### Scenario: Severity filter hides info
- **WHEN** running `lexictl validate --severity warning`
- **THEN** only error and warning issues are displayed; info issues are excluded

#### Scenario: Severity filter shows errors only
- **WHEN** running `lexictl validate --severity error`
- **THEN** only error issues are displayed

### Requirement: Validate supports single check mode
The `lexictl validate --check <name>` option SHALL run only the named check function.

#### Scenario: Single check mode
- **WHEN** running `lexictl validate --check hash_freshness`
- **THEN** only the hash freshness check runs and its results are displayed

#### Scenario: Invalid check name
- **WHEN** running `lexictl validate --check nonexistent`
- **THEN** an error message lists the available check names and exits with code 1

### Requirement: Validate supports JSON output
The `lexictl validate --json` option SHALL output the validation report as valid JSON to stdout, suitable for programmatic consumption.

#### Scenario: JSON output is valid
- **WHEN** running `lexictl validate --json`
- **THEN** stdout contains valid JSON with "issues" and "summary" keys

#### Scenario: JSON output with severity filter
- **WHEN** running `lexictl validate --json --severity warning`
- **THEN** the JSON output only contains issues at warning or error severity
