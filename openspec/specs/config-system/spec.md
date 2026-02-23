# config-system Specification

## Purpose
TBD - created by archiving change phase-1-foundation. Update Purpose after archive.
## Requirements
### Requirement: Config schema with defaults
Nested Pydantic model hierarchy (LexibraryConfig, LLMConfig, TokenizerConfig, CrawlConfig, IgnoreConfig, DaemonConfig, OutputConfig, ASTConfig) with sensible defaults. `LexibraryConfig` SHALL include a `scope_root: str` field (default: `"."`) specifying which files get design files — relative to project root. `CrawlConfig` SHALL include a `max_file_size_kb: int` field (default: `512`) — files exceeding this size are skipped during `update_project` with a log warning. `TokenBudgetConfig` SHALL NOT include a `handoff_tokens` field (removed — HANDOFF.md replaced by IWH).

#### Scenario: Default scope_root
- **WHEN** config is loaded without a `scope_root` field
- **THEN** `scope_root` SHALL default to `"."`

#### Scenario: Custom scope_root
- **WHEN** config contains `scope_root: "src/"`
- **THEN** `LexibraryConfig.scope_root` SHALL be `"src/"`

#### Scenario: Default max_file_size_kb
- **WHEN** config is loaded without `crawl.max_file_size_kb`
- **THEN** `CrawlConfig.max_file_size_kb` SHALL default to `512`

#### Scenario: No handoff_tokens in TokenBudgetConfig
- **WHEN** creating a default `TokenBudgetConfig`
- **THEN** the model SHALL NOT have a `handoff_tokens` attribute

#### Scenario: Stale handoff_tokens silently ignored
- **WHEN** loading a config YAML that contains `token_budgets.handoff_tokens: 100`
- **THEN** the config SHALL load without error (Pydantic `extra="ignore"` handles stale keys)

### Requirement: Config file discovery
The system SHALL search for the project config at `.lexibrary/config.yaml` relative to the project root (found via `find_project_root()`). The global config SHALL be read from `~/.config/lexibrary/config.yaml` (XDG base directory).

#### Scenario: Project config file is found via project root
- **WHEN** calling `load_config()` from a directory whose project root contains `.lexibrary/config.yaml`
- **THEN** it loads and returns the project config merged over the global config

#### Scenario: Global config is read from XDG path
- **WHEN** `~/.config/lexibrary/config.yaml` exists and `.lexibrary/config.yaml` does not
- **THEN** the global config is loaded as-is with all defaults applied

#### Scenario: Neither config file exists
- **WHEN** no global config and no project config exist
- **THEN** `load_config()` returns a `LexibraryConfig` with all defaults

### Requirement: Config loading and validation
The system SHALL load YAML files via PyYAML, validate against the Pydantic schema, and return a `LexibraryConfig`. Two-tier merge: load global → load project → merge with project values taking precedence.

#### Scenario: Config is loaded from YAML file
- **WHEN** calling `load_config()` with a valid `.lexibrary/config.yaml`
- **THEN** it parses the YAML and returns a `LexibraryConfig` with values from the file

#### Scenario: Invalid YAML raises ValidationError
- **WHEN** calling `load_config()` with a YAML file containing type-mismatched values (e.g., timeout as string)
- **THEN** Pydantic raises a `ValidationError`

#### Scenario: Project config overrides global config
- **WHEN** global config sets `llm.model = "claude-opus-4-6"` and project config sets `llm.model = "claude-haiku-4-5-20251001"`
- **THEN** the merged config has `llm.model == "claude-haiku-4-5-20251001"`

#### Scenario: Partial project config merges with global defaults
- **WHEN** the project config only specifies `llm.provider = "anthropic"` and global config provides all other fields
- **THEN** the merged config has the project's LLM provider and global defaults for all other fields

### Requirement: Config template for initialization
DEFAULT_CONFIG_TEMPLATE string SHALL NOT include `handoff_tokens` in the `token_budgets` section. The template SHALL include all other existing token budget fields.

#### Scenario: Template does not include handoff_tokens
- **WHEN** the config template is rendered
- **THEN** it SHALL NOT contain `handoff_tokens`

#### Scenario: Template includes remaining token budgets
- **WHEN** the config template is rendered
- **THEN** it SHALL contain `start_here_tokens`, `design_file_tokens`, `design_file_abridged_tokens`, `aindex_tokens`, and `concept_file_tokens`

### Requirement: Mapping strategy config stub
The system SHALL define a `MappingConfig` Pydantic model with a `strategies` field (list of mapping rules, default empty list). The mapping strategies are not evaluated in Phase 1; the model stub locks in the YAML key name so Phase 4 can populate it without breaking existing project configs.

#### Scenario: MappingConfig accepts empty strategies list
- **WHEN** creating a `MappingConfig` with no arguments
- **THEN** `mapping_config.strategies` returns an empty list

#### Scenario: MappingConfig stub does not raise on unknown strategy entries
- **WHEN** loading a project config with a populated `mapping.strategies` list
- **THEN** the config loads without error (entries stored as raw dicts until Phase 4 defines the strategy models)

### Requirement: CrawlConfig with binary extensions
The `CrawlConfig` Pydantic model in `src/lexibrary/config/schema.py` SHALL include a `binary_extensions: list[str]` field containing file extensions (with leading dot) that are treated as binary. Files with these extensions SHALL be described as `"Binary file (.ext)"` by the index generator rather than having their lines counted.

The field SHALL default to a comprehensive list covering: image formats (`.png`, `.jpg`, `.jpeg`, `.gif`, `.ico`, `.svg`, `.webp`), audio/video (`.mp3`, `.mp4`, `.wav`, `.ogg`, `.webm`), fonts (`.woff`, `.woff2`, `.ttf`, `.eot`), archives (`.zip`, `.tar`, `.gz`, `.bz2`, `.7z`, `.rar`), documents (`.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`), executables/compiled (`.exe`, `.dll`, `.so`, `.dylib`, `.pyc`, `.pyo`, `.class`, `.o`, `.obj`), and database (`.sqlite`, `.db`).

`CrawlConfig` SHALL also be wired into `LexibraryConfig` as `crawl: CrawlConfig = Field(default_factory=CrawlConfig)`.

#### Scenario: CrawlConfig added to LexibraryConfig
- **WHEN** a default `LexibraryConfig` is created
- **THEN** it SHALL have a `crawl` attribute that is a `CrawlConfig` instance

#### Scenario: Default binary extensions include common formats
- **WHEN** a `CrawlConfig` is created with default values
- **THEN** `binary_extensions` SHALL contain at least `.png`, `.jpg`, `.pyc`, `.zip`, `.exe`, `.pdf`, `.mp4`

#### Scenario: Custom binary extensions override defaults
- **WHEN** `LexibraryConfig` is loaded from a config file specifying `crawl.binary_extensions`
- **THEN** `config.crawl.binary_extensions` SHALL contain only the configured values

#### Scenario: CrawlConfig tolerates extra fields
- **WHEN** a `CrawlConfig` is created with an unknown extra field
- **THEN** the extra field SHALL be ignored (not raise a validation error)

### Requirement: IWHConfig model
The system SHALL define an `IWHConfig` Pydantic model with `model_config = ConfigDict(extra="ignore")` and a single field `enabled: bool` (default: `True`).

#### Scenario: IWHConfig default
- **WHEN** creating `IWHConfig()` with no arguments
- **THEN** `enabled` SHALL be `True`

#### Scenario: IWHConfig tolerates extra fields
- **WHEN** creating `IWHConfig` with an unknown extra field
- **THEN** the extra field SHALL be ignored (not raise a validation error)

### Requirement: IWHConfig re-exported from config package
`IWHConfig` SHALL be importable from `lexibrary.config`.

#### Scenario: Import IWHConfig
- **WHEN** running `from lexibrary.config import IWHConfig`
- **THEN** the import SHALL succeed

### Requirement: Config template includes new sections
`DEFAULT_PROJECT_CONFIG_TEMPLATE` SHALL include `project_name`, `agent_environment`, and `iwh` sections with defaults and explanatory comments.

#### Scenario: Template includes project_name
- **WHEN** the config template is rendered
- **THEN** it SHALL contain `project_name: ""` with a comment

#### Scenario: Template includes agent_environment
- **WHEN** the config template is rendered
- **THEN** it SHALL contain `agent_environment: []` with a comment

#### Scenario: Template includes iwh section
- **WHEN** the config template is rendered
- **THEN** it SHALL contain an `iwh:` section with `enabled: true`

### Requirement: DaemonConfig schema
The `DaemonConfig` Pydantic model SHALL have the following fields with updated defaults:

- `debounce_seconds: float = 2.0` (unchanged)
- `sweep_interval_seconds: int = 3600` (changed from 300)
- `sweep_skip_if_unchanged: bool = True` (new)
- `git_suppression_seconds: int = 5` (new)
- `watchdog_enabled: bool = False` (new, replaces `enabled`)
- `log_level: str = "info"` (new)

The `enabled: bool = True` field SHALL be removed. The `extra="ignore"` config ensures existing configs with `daemon.enabled` are silently ignored.

#### Scenario: Default DaemonConfig values
- **WHEN** a `DaemonConfig` is created with no arguments
- **THEN** `debounce_seconds` SHALL be `2.0`
- **AND** `sweep_interval_seconds` SHALL be `3600`
- **AND** `sweep_skip_if_unchanged` SHALL be `True`
- **AND** `git_suppression_seconds` SHALL be `5`
- **AND** `watchdog_enabled` SHALL be `False`
- **AND** `log_level` SHALL be `"info"`

#### Scenario: Old enabled field silently ignored
- **WHEN** a `DaemonConfig` is created from YAML containing `enabled: true`
- **THEN** the field SHALL be silently ignored due to `extra="ignore"`
- **AND** no error SHALL be raised

### Requirement: Default config template updated
The `DEFAULT_PROJECT_CONFIG_TEMPLATE` in `config/defaults.py` SHALL reflect the new `DaemonConfig` fields.

#### Scenario: Template contains new daemon fields
- **WHEN** the default config template is rendered
- **THEN** it SHALL include `sweep_skip_if_unchanged: true`
- **AND** it SHALL include `git_suppression_seconds: 5`
- **AND** it SHALL include `watchdog_enabled: false`
- **AND** it SHALL include `log_level: info`
- **AND** it SHALL include `sweep_interval_seconds: 3600`
- **AND** it SHALL NOT include `enabled: true`

