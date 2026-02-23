## ADDED Requirements

### Requirement: Init command creates config file
The `lexi init` command SHALL create a `lexibrary.toml` file in the target directory using a provider-aware template. It MUST accept a `--provider` option (default: `"anthropic"`, choices: `"anthropic"`, `"openai"`, `"ollama"`) that sets the LLM provider, model, and API key environment variable in the generated config.

#### Scenario: Init creates config with default provider
- **WHEN** running `lexi init` in an empty directory
- **THEN** a `lexibrary.toml` file is created with `provider = "anthropic"`, `model = "claude-sonnet-4-5-20250514"`, and `api_key_env = "ANTHROPIC_API_KEY"`

#### Scenario: Init creates config with OpenAI provider
- **WHEN** running `lexi init --provider openai`
- **THEN** the generated `lexibrary.toml` contains `provider = "openai"`, `model = "gpt-4o-mini"`, and `api_key_env = "OPENAI_API_KEY"`

#### Scenario: Init creates config with Ollama provider
- **WHEN** running `lexi init --provider ollama`
- **THEN** the generated `lexibrary.toml` contains `provider = "ollama"`, `model = "llama3.2"`, and `api_key_env = ""`

#### Scenario: Init fails if config already exists
- **WHEN** running `lexi init` in a directory that already contains `lexibrary.toml`
- **THEN** the command prints a warning message and exits with code 1 without modifying the existing file

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
