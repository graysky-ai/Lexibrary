# convention-config Specification

## Purpose
TBD - created by archiving change conventions-uplift. Update Purpose after archive.
## Requirements
### Requirement: ConventionConfig model
The system SHALL define a `ConventionConfig` Pydantic 2 model in `src/lexibrary/config/schema.py` with:
- `lookup_display_limit` (int) — maximum conventions shown in `lexi lookup`, default `5`
- `model_config = ConfigDict(extra="ignore")`

`LexibraryConfig` SHALL include a `conventions: ConventionConfig` field with `default_factory=ConventionConfig`.

#### Scenario: Default ConventionConfig
- **WHEN** a `ConventionConfig` is created with no arguments
- **THEN** `lookup_display_limit` SHALL be `5`

#### Scenario: Custom display limit
- **WHEN** config YAML contains `conventions: { lookup_display_limit: 10 }`
- **THEN** `config.conventions.lookup_display_limit` SHALL be `10`

#### Scenario: ConventionConfig tolerates extra fields
- **WHEN** a `ConventionConfig` is created with an unknown extra field
- **THEN** the extra field SHALL be ignored

#### Scenario: ConventionConfig accessible from LexibraryConfig
- **WHEN** a default `LexibraryConfig` is created
- **THEN** `config.conventions` SHALL be a `ConventionConfig` instance with default values

### Requirement: User-declared conventions in config
`LexibraryConfig` SHALL include a `convention_declarations: list[ConventionDeclaration]` field (default empty list) for seeding conventions from config.

`ConventionDeclaration` SHALL be a Pydantic 2 model with:
- `body` (str) — the convention rule text (required)
- `scope` (str) — scope identifier, default `"project"`
- `tags` (list[str]) — categorization tags, default empty list

These declarations are materialized into `.lexibrary/conventions/` files by the build pipeline with `source: config` and `status: active`.

#### Scenario: Config with convention declarations
- **WHEN** config YAML contains `convention_declarations: [{body: "Use UTC everywhere", scope: project, tags: [time]}]`
- **THEN** `config.convention_declarations` SHALL contain one `ConventionDeclaration` with the correct values

#### Scenario: Empty declarations by default
- **WHEN** a default `LexibraryConfig` is created
- **THEN** `config.convention_declarations` SHALL be an empty list

#### Scenario: Declaration with minimal fields
- **WHEN** a `ConventionDeclaration` is created with only `body="No bare prints"`
- **THEN** `scope` SHALL default to `"project"` and `tags` SHALL default to `[]`

### Requirement: TokenBudgetConfig includes convention_file_tokens
`TokenBudgetConfig` SHALL include a `convention_file_tokens` field (int, default `500`) specifying the target token budget for individual convention files.

#### Scenario: Default convention_file_tokens
- **WHEN** a default `TokenBudgetConfig` is created
- **THEN** `convention_file_tokens` SHALL be `500`

#### Scenario: Custom convention_file_tokens
- **WHEN** config YAML contains `token_budgets: { convention_file_tokens: 800 }`
- **THEN** `config.token_budgets.convention_file_tokens` SHALL be `800`

### Requirement: ConventionConfig re-exported from config package
`ConventionConfig` and `ConventionDeclaration` SHALL be importable from `lexibrary.config`.

#### Scenario: Import ConventionConfig
- **WHEN** `from lexibrary.config import ConventionConfig` is used
- **THEN** the import SHALL succeed

#### Scenario: Import ConventionDeclaration
- **WHEN** `from lexibrary.config import ConventionDeclaration` is used
- **THEN** the import SHALL succeed

