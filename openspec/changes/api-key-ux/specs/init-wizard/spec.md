## MODIFIED Requirements

### Requirement: WizardAnswers dataclass
The system SHALL define a `WizardAnswers` dataclass that collects all wizard step outputs:
- `project_name: str` (default: `""`)
- `scope_root: str` (default: `"."`)
- `agent_environments: list[str]` (default: `[]`)
- `llm_provider: str` (default: `"anthropic"`)
- `llm_model: str` (default: `"claude-sonnet-4-6"`)
- `llm_api_key_env: str` (default: `"ANTHROPIC_API_KEY"`)
- `llm_api_key_source: str` (default: `"env"`)
- `llm_api_key_value: str` (default: `""`) — in-memory only, never written to config
- `ignore_patterns: list[str]` (default: `[]`)
- `token_budgets_customized: bool` (default: `False`)
- `token_budgets: dict[str, int]` (default: `{}`)
- `iwh_enabled: bool` (default: `True`)
- `confirmed: bool` (default: `False`)

#### Scenario: WizardAnswers has correct defaults
- **WHEN** creating a `WizardAnswers()` with no arguments
- **THEN** all fields SHALL have their documented default values including `llm_api_key_source == "env"` and `llm_api_key_value == ""`

### Requirement: Step 4 — LLM Provider
The wizard SHALL detect available LLM providers using `detect_llm_providers()`, display a transparency message ("We never store, log, or transmit your API key"), and prompt for the provider. After selecting a provider it SHALL present a storage-method sub-step with three options: `env` (already in shell environment), `dotenv` (store in `.env` file at project root), and `manual` (user will manage the key themselves). If `dotenv` is chosen, the wizard SHALL prompt for the key value (using `rich.prompt.Prompt` with `password=True`), write it to `project_root/.env` via `dotenv.set_key()`, and ensure `.env` is appended to `.gitignore` if not already present.

#### Scenario: Provider detected and env storage accepted
- **WHEN** `ANTHROPIC_API_KEY` is set in the shell and the user selects `env` storage
- **THEN** `answers.llm_provider` SHALL be `"anthropic"`, `answers.llm_api_key_env` SHALL be `"ANTHROPIC_API_KEY"`, `answers.llm_api_key_source` SHALL be `"env"`, and `answers.llm_api_key_value` SHALL be `""`

#### Scenario: No provider detected, no change to storage sub-step
- **WHEN** no API key env vars are set
- **THEN** the wizard SHALL still offer all three storage options; if `dotenv` is chosen it SHALL prompt for the key value

#### Scenario: Dotenv storage chosen — key written to .env
- **WHEN** the user selects `dotenv` storage and enters an API key value
- **THEN** `answers.llm_api_key_source` SHALL be `"dotenv"`, `dotenv.set_key(project_root / ".env", key_env_var, key_value)` SHALL be called, and `.env` SHALL be present in `project_root/.gitignore`

#### Scenario: Dotenv storage chosen — .env already gitignored
- **WHEN** the user selects `dotenv` storage and `.gitignore` already contains `.env`
- **THEN** the wizard SHALL NOT add a duplicate `.env` entry to `.gitignore`

#### Scenario: Manual storage chosen
- **WHEN** the user selects `manual` storage
- **THEN** `answers.llm_api_key_source` SHALL be `"manual"` and `answers.llm_api_key_value` SHALL be `""` (no key prompt)

#### Scenario: api_key_value never appears in summary table
- **WHEN** the wizard reaches the Step 8 summary
- **THEN** the table SHALL display `"[stored in .env]"` for dotenv mode, `"[from environment]"` for env mode, or `"[manual]"` for manual mode — never the raw key value

#### Scenario: use_defaults mode selects env storage
- **WHEN** `run_wizard(use_defaults=True)` is called
- **THEN** `answers.llm_api_key_source` SHALL be `"env"` (the safe default)

## ADDED Requirements

### Requirement: Step 4 storage sub-step in use_defaults mode
When `use_defaults=True`, the wizard SHALL skip the storage-method prompt and select `"env"` as the default `api_key_source` without writing a `.env` file.

#### Scenario: Defaults mode does not write .env
- **WHEN** `run_wizard(use_defaults=True)` completes
- **THEN** no `.env` file SHALL be created and `answers.llm_api_key_value` SHALL be `""`
