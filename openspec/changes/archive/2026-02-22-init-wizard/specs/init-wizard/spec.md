## ADDED Requirements

### Requirement: WizardAnswers dataclass
The system SHALL define a `WizardAnswers` dataclass that collects all wizard step outputs:
- `project_name: str` (default: `""`)
- `scope_root: str` (default: `"."`)
- `agent_environments: list[str]` (default: `[]`)
- `llm_provider: str` (default: `"anthropic"`)
- `llm_model: str` (default: `"claude-sonnet-4-6"`)
- `llm_api_key_env: str` (default: `"ANTHROPIC_API_KEY"`)
- `ignore_patterns: list[str]` (default: `[]`)
- `token_budgets_customized: bool` (default: `False`)
- `token_budgets: dict[str, int]` (default: `{}`)
- `iwh_enabled: bool` (default: `True`)
- `confirmed: bool` (default: `False`)

#### Scenario: WizardAnswers has correct defaults
- **WHEN** creating a `WizardAnswers()` with no arguments
- **THEN** all fields SHALL have their documented default values

### Requirement: run_wizard function
`run_wizard(project_root: Path, console: Console, *, use_defaults: bool = False) -> WizardAnswers | None` SHALL orchestrate the 8-step wizard flow. It SHALL return `WizardAnswers` if the user confirmed, or `None` if the user cancelled at the summary step.

#### Scenario: Wizard returns answers on confirm
- **WHEN** `run_wizard()` is called and user confirms at summary step
- **THEN** the function SHALL return a `WizardAnswers` with `confirmed=True`

#### Scenario: Wizard returns None on cancel
- **WHEN** `run_wizard()` is called and user declines at summary step
- **THEN** the function SHALL return `None`

### Requirement: use_defaults mode
When `use_defaults=True`, the wizard SHALL accept all auto-detected values and defaults without prompting the user. It SHALL still run all detection steps and set `confirmed=True`.

#### Scenario: Defaults mode skips prompts
- **WHEN** `run_wizard(use_defaults=True)` is called
- **THEN** the function SHALL return answers using detection results and defaults without any interactive prompts

#### Scenario: Defaults mode uses detected project name
- **WHEN** `use_defaults=True` and `pyproject.toml` contains `name = "my-app"`
- **THEN** `answers.project_name` SHALL be `"my-app"`

### Requirement: Step 1 — Project Name
The wizard SHALL detect the project name using `detect_project_name()`, display the detected value and source, and prompt for confirmation or override via `rich.prompt.Prompt`.

#### Scenario: Detected name accepted
- **WHEN** the user accepts the detected project name
- **THEN** `answers.project_name` SHALL be the detected name

#### Scenario: Detected name overridden
- **WHEN** the user provides an alternative name
- **THEN** `answers.project_name` SHALL be the user-provided name

### Requirement: Step 2 — Scope Root
The wizard SHALL detect scope roots using `detect_scope_roots()`, display suggestions, and prompt for the scope root path. It SHALL show a "Modify later" hint pointing to `config.yaml`.

#### Scenario: Detected scope root accepted
- **WHEN** `src/` is detected and user accepts
- **THEN** `answers.scope_root` SHALL be `"src/"`

#### Scenario: Default scope root when nothing detected
- **WHEN** no common directories are detected and user accepts default
- **THEN** `answers.scope_root` SHALL be `"."`

### Requirement: Step 3 — Agent Environment
The wizard SHALL detect agent environments using `detect_agent_environments()`, display detected environments, and allow multi-select via comma-separated input. It SHALL check for existing Lexibrary sections via `check_existing_agent_rules()` and advise the user if found. If a selected agent environment directory doesn't exist, the wizard SHALL ask before creating it.

#### Scenario: Detected environments accepted
- **WHEN** `.claude/` is detected and user accepts
- **THEN** `answers.agent_environments` SHALL contain `"claude"`

#### Scenario: Multiple environments selected
- **WHEN** user enters `"claude, cursor"` at the prompt
- **THEN** `answers.agent_environments` SHALL contain both `"claude"` and `"cursor"`

#### Scenario: Existing marker found
- **WHEN** `check_existing_agent_rules()` finds a marker in `CLAUDE.md`
- **THEN** the wizard SHALL display an advisory message about the existing section

### Requirement: Step 4 — LLM Provider
The wizard SHALL detect available LLM providers using `detect_llm_providers()`, display a transparency message ("We never store, log, or transmit your API key"), and store only the provider name and env var name. If no env var is found, it SHALL advise the user what to set.

#### Scenario: Provider detected and accepted
- **WHEN** `ANTHROPIC_API_KEY` is set and user accepts
- **THEN** `answers.llm_provider` SHALL be `"anthropic"` and `answers.llm_api_key_env` SHALL be `"ANTHROPIC_API_KEY"`

#### Scenario: No provider detected
- **WHEN** no API key env vars are set
- **THEN** the wizard SHALL display guidance on which env var to set and use anthropic as default

#### Scenario: API key value never prompted
- **WHEN** the wizard runs Step 4
- **THEN** it SHALL NOT prompt for the actual API key value at any point

### Requirement: Step 5 — Ignore Patterns
The wizard SHALL detect the project type using `detect_project_type()`, suggest patterns via `suggest_ignore_patterns()`, and prompt for acceptance or override.

#### Scenario: Suggested patterns accepted
- **WHEN** project type is "python" and user accepts suggestions
- **THEN** `answers.ignore_patterns` SHALL contain the python-specific patterns

#### Scenario: No project type detected
- **WHEN** `detect_project_type()` returns `None`
- **THEN** `answers.ignore_patterns` SHALL default to an empty list

### Requirement: Step 6 — Token Budgets
The wizard SHALL display default token budget values and offer to customize individual values.

#### Scenario: Defaults accepted
- **WHEN** user accepts default budgets
- **THEN** `answers.token_budgets_customized` SHALL be `False`

#### Scenario: Custom budgets provided
- **WHEN** user opts to customize and sets `design_file_tokens` to 500
- **THEN** `answers.token_budgets_customized` SHALL be `True` and `answers.token_budgets` SHALL contain the custom value

### Requirement: Step 7 — I Was Here
The wizard SHALL briefly explain the IWH system and prompt for enable/disable toggle.

#### Scenario: IWH enabled by default
- **WHEN** user accepts the default
- **THEN** `answers.iwh_enabled` SHALL be `True`

#### Scenario: IWH disabled
- **WHEN** user disables IWH
- **THEN** `answers.iwh_enabled` SHALL be `False`

### Requirement: Step 8 — Summary and Confirm
The wizard SHALL display all collected answers in a Rich table and prompt for confirmation via `rich.prompt.Confirm`.

#### Scenario: User confirms
- **WHEN** user answers Yes at the summary
- **THEN** `answers.confirmed` SHALL be `True` and `run_wizard()` returns the answers

#### Scenario: User cancels
- **WHEN** user answers No at the summary
- **THEN** `run_wizard()` SHALL return `None`

### Requirement: Interactive prompts use rich.prompt
All interactive user input SHALL use `rich.prompt.Prompt` and `rich.prompt.Confirm`. The wizard SHALL NOT use `typer.prompt()`, bare `input()`, or any other input mechanism.

#### Scenario: Prompt uses rich.prompt.Prompt
- **WHEN** the wizard asks for text input
- **THEN** it SHALL use `rich.prompt.Prompt.ask()`

#### Scenario: Confirm uses rich.prompt.Confirm
- **WHEN** the wizard asks for yes/no confirmation
- **THEN** it SHALL use `rich.prompt.Confirm.ask()`
