# api-key-source Specification

## Purpose
TBD - created by archiving change api-key-ux. Update Purpose after archive.
## Requirements
### Requirement: api_key_source config field
`LLMConfig` SHALL include an `api_key_source: str` field with a default value of `"env"`. Valid values are `"env"`, `"dotenv"`, and `"manual"`. `LexibraryConfig` defaults template SHALL include `api_key_source: env` under the `llm:` section with a comment explaining the options.

#### Scenario: Default api_key_source is env
- **WHEN** a `LLMConfig` is created without specifying `api_key_source`
- **THEN** `config.llm.api_key_source` SHALL be `"env"`

#### Scenario: api_key_source loaded from YAML
- **WHEN** `.lexibrary/config.yaml` contains `llm.api_key_source: dotenv`
- **THEN** `config.llm.api_key_source` SHALL be `"dotenv"`

#### Scenario: Unknown api_key_source value is ignored gracefully
- **WHEN** config YAML contains `llm.api_key_source: "unknown"`
- **THEN** Pydantic SHALL accept the string value without error (no enum enforcement at schema level)

### Requirement: Dotenv loading at CLI startup
Both CLI entry point apps (`lexi_app` and `lexictl_app`) SHALL attempt to load a `.env` file from the project root when `api_key_source == "dotenv"` is set in the raw project config. Loading SHALL use `python-dotenv`'s `load_dotenv(path, override=False)` so that env vars already set in the shell are not clobbered.

#### Scenario: Dotenv loaded when api_key_source is dotenv
- **WHEN** `.lexibrary/config.yaml` contains `llm.api_key_source: dotenv` and `project_root/.env` exists
- **THEN** the CLI startup SHALL call `load_dotenv(project_root / ".env", override=False)` before config validation or LLM initialisation

#### Scenario: Dotenv not loaded when api_key_source is env
- **WHEN** `api_key_source` is `"env"` (default)
- **THEN** the CLI startup SHALL NOT call `load_dotenv()` and SHALL rely entirely on shell environment variables

#### Scenario: Dotenv loading skipped outside a project
- **WHEN** `find_project_root()` returns `None` (user is outside a Lexibrary project)
- **THEN** dotenv loading SHALL be skipped silently; the normal project-not-found error surfaces later

#### Scenario: Dotenv file missing does not crash CLI
- **WHEN** `api_key_source == "dotenv"` but no `.env` file exists at the project root
- **THEN** `load_dotenv()` SHALL return without error and the CLI SHALL continue normally

#### Scenario: Existing env var not clobbered by dotenv
- **WHEN** `ANTHROPIC_API_KEY` is already set in the shell and `.env` also defines `ANTHROPIC_API_KEY`
- **THEN** the shell value SHALL take precedence (`override=False`)

### Requirement: python-dotenv dependency
`python-dotenv` SHALL be added as a project dependency with version bounds `>=1.0.0,<2.0.0`.

#### Scenario: python-dotenv importable
- **WHEN** the project is installed via `uv sync`
- **THEN** `import dotenv` SHALL succeed without error

