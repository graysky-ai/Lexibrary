## MODIFIED Requirements

### Requirement: Init command
The `lexi init` command SHALL accept a path argument (default ".") and a `--provider` option (default "anthropic"). It MUST create a `lexibrary.toml` config file, manage `.gitignore` entries, and display next-steps guidance. If the config file already exists, it MUST exit with code 1.

#### Scenario: Init command accepts path argument
- **WHEN** running `lexi init /some/path`
- **THEN** the command creates `lexibrary.toml` in `/some/path`

#### Scenario: Init command defaults to current directory
- **WHEN** running `lexi init` with no path argument
- **THEN** the command operates on the current directory

#### Scenario: Init command has help text
- **WHEN** running `lexi init --help`
- **THEN** the help text says "Initialize Lexibrary in a project. Creates lexibrary.toml config file."

#### Scenario: Init command accepts provider option
- **WHEN** running `lexi init --provider openai`
- **THEN** the generated config uses OpenAI provider settings

### Requirement: Crawl command
The `lexi crawl` command SHALL accept a path argument (default ".") and options `--full` (force re-crawl), `--dry-run` (preview only), and `--verbose` (debug logging). It MUST run the crawler engine with a progress bar and print a summary table of results.

#### Scenario: Crawl command accepts path argument
- **WHEN** running `lexi crawl /some/path`
- **THEN** the command crawls the specified directory

#### Scenario: Crawl command defaults to current directory
- **WHEN** running `lexi crawl` with no path argument
- **THEN** the command crawls the current directory

#### Scenario: Crawl command has help text
- **WHEN** running `lexi crawl --help`
- **THEN** the help text says "Run the Lexibrary crawler. Generates .aindex files for all directories."

#### Scenario: Crawl command accepts full flag
- **WHEN** running `lexi crawl --full`
- **THEN** the cache is cleared before crawling

#### Scenario: Crawl command accepts dry-run flag
- **WHEN** running `lexi crawl --dry-run`
- **THEN** no files are written and output indicates dry run

### Requirement: Daemon command
The `lexi daemon` command SHALL accept a path argument (default ".") and a `--foreground` flag. It MUST start the daemon service when Phase 7 is implemented, or display a "not yet available" message otherwise.

#### Scenario: Daemon command accepts path argument
- **WHEN** running `lexi daemon /some/path`
- **THEN** the command targets the specified directory

#### Scenario: Daemon command defaults to current directory
- **WHEN** running `lexi daemon` with no path argument
- **THEN** the command targets the current directory

#### Scenario: Daemon command has help text
- **WHEN** running `lexi daemon --help`
- **THEN** the help text says "Start the Lexibrary background daemon for live re-indexing."

#### Scenario: Daemon command accepts foreground flag
- **WHEN** running `lexi daemon --foreground`
- **THEN** the `--foreground` flag is recognized and passed to the daemon service

### Requirement: Status command
The `lexi status` command SHALL accept a path argument (default ".") and display a Rich panel with config info, index counts, cache counts, stale file counts, and daemon status.

#### Scenario: Status command accepts path argument
- **WHEN** running `lexi status /some/path`
- **THEN** the command checks status for the specified directory

#### Scenario: Status command defaults to current directory
- **WHEN** running `lexi status` with no path argument
- **THEN** the command checks the current directory

#### Scenario: Status command has help text
- **WHEN** running `lexi status --help`
- **THEN** the help text says "Show indexing status: files indexed, stale files, daemon status."

### Requirement: Clean command
The `lexi clean` command SHALL accept a path argument (default ".") and a `--yes` flag to skip confirmation. It MUST remove all `.aindex` files, the cache file, and the log file, with an interactive confirmation prompt unless `--yes` is provided.

#### Scenario: Clean command accepts path argument
- **WHEN** running `lexi clean /some/path`
- **THEN** the command cleans the specified directory

#### Scenario: Clean command defaults to current directory
- **WHEN** running `lexi clean` with no path argument
- **THEN** the command cleans the current directory

#### Scenario: Clean command has help text
- **WHEN** running `lexi clean --help`
- **THEN** the help text says "Remove all .aindex files and the cache from the project."

#### Scenario: Clean command accepts yes flag
- **WHEN** running `lexi clean --yes`
- **THEN** files are removed without prompting for confirmation
