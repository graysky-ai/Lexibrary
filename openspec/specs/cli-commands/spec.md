# cli-commands Specification

## Purpose
TBD - created by archiving change lexi-cli. Update Purpose after archive.
## Requirements
### Requirement: Init command creates config file
The `lexictl init` command SHALL run the interactive setup wizard to create a `.lexibrary/` directory with a dynamically generated `config.yaml`. It MUST accept a `--defaults` flag that accepts all auto-detected values without prompting (for CI/scripting use).

#### Scenario: Init runs wizard
- **WHEN** running `lexictl init` in a fresh directory
- **THEN** the wizard SHALL run and create `.lexibrary/` with a config derived from wizard answers

#### Scenario: Init with --defaults skips prompts
- **WHEN** running `lexictl init --defaults` in a fresh directory
- **THEN** the wizard SHALL use all detected/default values without prompting and create `.lexibrary/`

#### Scenario: Init fails if already initialized
- **WHEN** running `lexictl init` in a directory that already contains `.lexibrary/`
- **THEN** the command SHALL print an error message pointing to `lexictl setup --update` and exit with code 1

#### Scenario: Init shows creation summary
- **WHEN** `lexictl init` completes successfully
- **THEN** the output SHALL include a count of items created and suggest running `lexictl update`

### Requirement: Init command manages gitignore
The `lexi init` command SHALL create or update a `.gitignore` file to include Lexibrary-specific entries (`.aindex`, `.lexibrary_cache.json`, `.lexibrary.log`, `.lexibrary.pid`).

#### Scenario: Init creates new gitignore
- **WHEN** running `lexi init` in a directory without a `.gitignore` file
- **THEN** a `.gitignore` file is created containing all Lexibrary entries under a `# Lexibrary` header

#### Scenario: Init updates existing gitignore
- **WHEN** running `lexi init` in a directory with an existing `.gitignore` that does not contain `.aindex`
- **THEN** the Lexibrary entries are appended to the existing `.gitignore` under a `# Lexibrary` header

#### Scenario: Init does not duplicate gitignore entries
- **WHEN** running `lexi init` in a directory with a `.gitignore` that already contains `.aindex`
- **THEN** the `.aindex` entry is NOT added again (only missing entries are appended)

### Requirement: Init shows next steps
The `lexi init` command SHALL print guidance after successful initialization telling the user to edit the config and run `lexi crawl`.

#### Scenario: Next steps displayed after init
- **WHEN** `lexi init` completes successfully
- **THEN** the output includes "Next steps" with instructions to edit `lexibrary.toml` and run `lexi crawl`

### Requirement: Config template renderer
The system SHALL provide a `render_default_config(provider: str)` function in `config/defaults.py` that returns a TOML string with provider-specific values substituted. Unknown providers MUST fall back to anthropic defaults.

#### Scenario: Render config for known provider
- **WHEN** calling `render_default_config("openai")`
- **THEN** the returned string contains `provider = "openai"` and `model = "gpt-4o-mini"`

#### Scenario: Render config for unknown provider
- **WHEN** calling `render_default_config("unknown_provider")`
- **THEN** the returned string uses anthropic defaults (`provider = "anthropic"`)

### Requirement: Crawl command runs indexer with progress
The `lexi crawl` command SHALL run the crawler engine and display a Rich progress bar showing the current directory being indexed. It MUST print a summary table after completion with directories indexed, files summarized, files cached, files skipped, LLM calls, and errors (if any).

#### Scenario: Crawl with progress output
- **WHEN** running `lexi crawl` in a configured project
- **THEN** a progress bar is displayed during crawling and a summary table is printed after completion

#### Scenario: Crawl full re-index
- **WHEN** running `lexi crawl --full`
- **THEN** the change detection cache is cleared before crawling, forcing all files to be re-processed

#### Scenario: Crawl dry run
- **WHEN** running `lexi crawl --dry-run`
- **THEN** the command reports what would be indexed but writes no `.aindex` files, and the output includes "Dry run complete"

#### Scenario: Crawl verbose logging
- **WHEN** running `lexi crawl --verbose`
- **THEN** debug-level logging is enabled and log output is written to the configured log file

### Requirement: Status command shows project state
The `lexi status` command SHALL display a Rich panel containing: config file path (or "not found"), LLM provider and model, tokenizer backend and model, count of directories with `.aindex` files, count of cached files, count of stale files, and daemon status (running/not running with PID).

#### Scenario: Status with no config file
- **WHEN** running `lexi status` in a directory without `lexibrary.toml`
- **THEN** the panel shows "not found (using defaults)" for the config file path and uses default values for all settings

#### Scenario: Status shows correct index counts
- **WHEN** running `lexi status` after a successful crawl
- **THEN** the panel shows the correct number of directories indexed and files cached

#### Scenario: Status detects stale files
- **WHEN** running `lexi status` after modifying a file that was previously indexed
- **THEN** the stale files count is greater than 0 and a suggestion to run `lexi crawl` is shown

#### Scenario: Status shows daemon status
- **WHEN** running `lexi status` with no daemon running
- **THEN** the daemon status shows "not running"

#### Scenario: Status detects stale PID file
- **WHEN** a `.lexibrary.pid` file exists but the PID does not correspond to a running process
- **THEN** the daemon status shows "not running (stale PID file)"

### Requirement: Clean command removes generated files
The `lexi clean` command SHALL find and remove all `.aindex` files, the cache file (`.lexibrary_cache.json`), and the log file (`.lexibrary.log`) from the project. It MUST prompt for confirmation unless `--yes` is provided.

#### Scenario: Clean with confirmation
- **WHEN** running `lexi clean` without `--yes`
- **THEN** the command shows how many files were found and prompts "Delete all?" before proceeding

#### Scenario: Clean with --yes flag
- **WHEN** running `lexi clean --yes`
- **THEN** all `.aindex` files, cache, and log files are removed without prompting

#### Scenario: Clean with nothing to clean
- **WHEN** running `lexi clean` in a directory with no Lexibrary-generated files
- **THEN** the command prints "Nothing to clean." and exits normally

### Requirement: Daemon command stub
The `lexi daemon` command SHALL accept a path argument and a `--foreground` flag. Until the daemon service is implemented (Phase 7), it MUST display a message indicating the feature is not yet available.

#### Scenario: Daemon command not yet implemented
- **WHEN** running `lexi daemon` before Phase 7 is implemented
- **THEN** the command prints a message indicating the daemon feature is not yet available

#### Scenario: Daemon command accepts foreground flag
- **WHEN** running `lexi daemon --foreground --help`
- **THEN** the help text shows the `--foreground` option

### Requirement: Rich console output
All CLI commands SHALL use `rich.console.Console` for output. No command SHALL use `typer.echo()` or bare `print()`.

#### Scenario: Output uses Rich formatting
- **WHEN** any CLI command produces output
- **THEN** the output is rendered through a Rich Console instance (supporting colors, tables, panels, and progress bars)

#### Scenario: Stack commands use Rich output
- **WHEN** any `lexi stack` sub-command produces output
- **THEN** the output is rendered through the same Rich Console instance

### Requirement: Index command generates .aindex for a directory
The `lexi index` command SHALL accept a `directory` argument (default `.`) and a `-r`/`--recursive` boolean flag (default `False`). It SHALL require an initialized `.lexibrary/` directory to be present (walk up from CWD to find it), and generate `.aindex` files via the indexer module.

Without `--recursive`: generates a single `.aindex` for the specified directory.
With `--recursive`: generates `.aindex` files for all directories in the tree bottom-up.

On completion, the command SHALL print a summary via `rich.console.Console` showing directories indexed, files found, and any errors.

#### Scenario: Index single directory writes .aindex
- **WHEN** running `lexi index src/` in a project with an initialized `.lexibrary/`
- **THEN** a `.aindex` file SHALL be written at `.lexibrary/src/.aindex` and the command exits with code 0

#### Scenario: Index recursive indexes all directories
- **WHEN** running `lexi index -r .`
- **THEN** `.aindex` files SHALL be written for all directories in the project tree (bottom-up) and the command exits with code 0

#### Scenario: Index fails without .lexibrary/
- **WHEN** running `lexi index src/` in a directory tree with no `.lexibrary/`
- **THEN** the command SHALL print an error message and exit with a non-zero code

#### Scenario: Index fails for nonexistent directory
- **WHEN** running `lexi index nonexistent/`
- **THEN** the command SHALL print an error message and exit with a non-zero code

#### Scenario: Index fails for directory outside project root
- **WHEN** running `lexi index /tmp/other/`
- **THEN** the command SHALL print an error message indicating the directory is outside the project root

#### Scenario: Index displays progress for recursive mode
- **WHEN** running `lexi index -r .` on a multi-directory project
- **THEN** Rich progress output SHALL be displayed during indexing

#### Scenario: Index displays summary on completion
- **WHEN** `lexi index` or `lexi index -r` completes
- **THEN** the output SHALL include a count of directories indexed and files found

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

### Requirement: Describe command updates .aindex billboard
`lexi describe <directory> "<description>"` SHALL update the billboard description in a directory's `.aindex` file.
- SHALL parse the existing `.aindex`
- SHALL update the billboard text
- SHALL re-serialize and write the `.aindex`

#### Scenario: Update directory description
- **WHEN** `lexi describe src/auth "Authentication and authorization services"` is run
- **THEN** the `.aindex` billboard for `src/auth/` SHALL be updated with the new description

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

### Requirement: Re-init guard
`lexictl init` SHALL check for an existing `.lexibrary/` directory before running the wizard. If found, it SHALL print an error message directing the user to `lexictl setup --update` and exit with code 1.

#### Scenario: Re-init blocked
- **WHEN** running `lexictl init` and `.lexibrary/` already exists
- **THEN** the command SHALL print `"Project already initialised"` and reference `lexictl setup --update`

### Requirement: Non-TTY detection
`lexictl init` SHALL detect when `stdin` is not a TTY. In non-interactive environments without `--defaults`, it SHALL print a message advising the user to use `--defaults` and exit with code 1.

#### Scenario: Non-TTY without --defaults
- **WHEN** `lexictl init` is invoked in a non-TTY environment without `--defaults`
- **THEN** the command SHALL print a message about non-interactive mode and exit with code 1

#### Scenario: Non-TTY with --defaults succeeds
- **WHEN** `lexictl init --defaults` is invoked in a non-TTY environment
- **THEN** the command SHALL proceed normally using defaults

### Requirement: Wizard cancellation exits cleanly
If the user cancels at the wizard summary step, `lexictl init` SHALL exit with code 1 without creating any files.

#### Scenario: User cancels wizard
- **WHEN** the user answers "No" at the wizard summary step
- **THEN** no `.lexibrary/` directory SHALL be created and exit code SHALL be 1

