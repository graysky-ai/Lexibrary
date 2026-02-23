## MODIFIED Requirements

### Requirement: Config schema with defaults
The system SHALL define a nested Pydantic 2 model hierarchy (LexibraryConfig, LLMConfig, TokenBudgetConfig, MappingConfig, IgnoreConfig, DaemonConfig) with sensible defaults for all settings. `model_config = ConfigDict(extra="ignore")` SHALL be set on all models so configs written for older versions do not fail validation.

#### Scenario: Default LLM config uses Anthropic
- **WHEN** creating a default LLMConfig
- **THEN** it has provider="anthropic", model="claude-sonnet-4-6", api_key_env="ANTHROPIC_API_KEY", max_retries=3, timeout=60

#### Scenario: Default token budget config has reasonable limits
- **WHEN** creating a default TokenBudgetConfig
- **THEN** it has start_here_tokens=800, handoff_tokens=100, design_file_tokens=400, design_file_abridged_tokens=100, aindex_tokens=200, concept_file_tokens=400

#### Scenario: Default ignore config includes .lexibrary generated files
- **WHEN** creating a default IgnoreConfig
- **THEN** additional_patterns includes ".lexibrary/START_HERE.md", ".lexibrary/HANDOFF.md", ".lexibrary/**/*.md", ".lexibrary/**/.aindex", "node_modules/", "__pycache__/", ".git/", ".venv/", "venv/", "*.lock"

#### Scenario: Extra fields in config file are silently ignored
- **WHEN** loading a config file that contains unknown top-level keys
- **THEN** Pydantic validates successfully and the unknown keys are ignored

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
The system SHALL provide a `DEFAULT_PROJECT_CONFIG_TEMPLATE` string that serves as a starter `.lexibrary/config.yaml` with all sections, sensible defaults, and explanatory comments in YAML format.

#### Scenario: Template contains all config sections in YAML
- **WHEN** reading the `DEFAULT_PROJECT_CONFIG_TEMPLATE`
- **THEN** it includes YAML sections for llm, token_budgets, mapping, ignore, and daemon with inline comments

## REMOVED Requirements

### Requirement: Crawl configuration
**Reason**: `CrawlConfig` with `binary_extensions` belonged to the v1 crawl pipeline which is retired in v2. Binary extension filtering moves to the crawler/AST parser in Phase 3.
**Migration**: Remove `CrawlConfig` from config schema. Binary extension handling will be re-introduced in Phase 3 under the AST parser configuration.

## ADDED Requirements

### Requirement: Mapping strategy config stub
The system SHALL define a `MappingConfig` Pydantic model with a `strategies` field (list of mapping rules, default empty list). The mapping strategies are not evaluated in Phase 1; the model stub locks in the YAML key name so Phase 4 can populate it without breaking existing project configs.

#### Scenario: MappingConfig accepts empty strategies list
- **WHEN** creating a `MappingConfig` with no arguments
- **THEN** `mapping_config.strategies` returns an empty list

#### Scenario: MappingConfig stub does not raise on unknown strategy entries
- **WHEN** loading a project config with a populated `mapping.strategies` list
- **THEN** the config loads without error (entries stored as raw dicts until Phase 4 defines the strategy models)
