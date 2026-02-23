## MODIFIED Requirements

### Requirement: Config schema with defaults
Nested Pydantic model hierarchy (LexibraryConfig, LLMConfig, TokenizerConfig, CrawlConfig, IgnoreConfig, DaemonConfig, OutputConfig, ASTConfig, IWHConfig) with sensible defaults. `LexibraryConfig` SHALL include a `scope_root: str` field (default: `"."`) specifying which files get design files — relative to project root. `CrawlConfig` SHALL include a `max_file_size_kb: int` field (default: `512`) — files exceeding this size are skipped during `update_project` with a log warning.

`LexibraryConfig` SHALL additionally include:
- `project_name: str` (default: `""`) — project name set during `lexictl init`
- `agent_environment: list[str]` (default: `[]`) — agent environments configured during init (e.g., `["claude", "cursor"]`)
- `iwh: IWHConfig` (default: `IWHConfig()`) — I Was Here configuration

#### Scenario: Default scope_root
- **WHEN** config is loaded without a `scope_root` field
- **THEN** `scope_root` SHALL default to `"."`

#### Scenario: Custom scope_root
- **WHEN** config contains `scope_root: "src/"`
- **THEN** `LexibraryConfig.scope_root` SHALL be `"src/"`

#### Scenario: Default max_file_size_kb
- **WHEN** config is loaded without `crawl.max_file_size_kb`
- **THEN** `CrawlConfig.max_file_size_kb` SHALL default to `512`

#### Scenario: Large file skipped
- **WHEN** a file exceeds `max_file_size_kb` during `update_project`
- **THEN** the file SHALL be skipped with a log warning

#### Scenario: Default project_name
- **WHEN** config is loaded without a `project_name` field
- **THEN** `project_name` SHALL default to `""`

#### Scenario: Default agent_environment
- **WHEN** config is loaded without an `agent_environment` field
- **THEN** `agent_environment` SHALL default to an empty list

#### Scenario: Default IWH config
- **WHEN** config is loaded without an `iwh` section
- **THEN** `iwh.enabled` SHALL default to `True`

#### Scenario: agent_environment from YAML
- **WHEN** config contains `agent_environment: ["claude", "cursor"]`
- **THEN** `LexibraryConfig.agent_environment` SHALL be `["claude", "cursor"]`

#### Scenario: IWH disabled in YAML
- **WHEN** config contains `iwh: { enabled: false }`
- **THEN** `LexibraryConfig.iwh.enabled` SHALL be `False`

## ADDED Requirements

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
