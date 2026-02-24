## MODIFIED Requirements

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
- `install_hooks: bool` (default: `False`)
- `confirmed: bool` (default: `False`)

#### Scenario: WizardAnswers has correct defaults
- **WHEN** creating a `WizardAnswers()` with no arguments
- **THEN** all fields SHALL have their documented default values including `install_hooks=False`

## ADDED Requirements

### Requirement: Step 9 — Git Hooks
The wizard SHALL prompt the user to install git hooks (pre-commit validation and post-commit auto-update) after the IWH step. It SHALL use `rich.prompt.Confirm` with a default of `True`.

#### Scenario: Hooks enabled by default
- **WHEN** user accepts the default at the hooks prompt
- **THEN** `answers.install_hooks` SHALL be `True`

#### Scenario: Hooks declined
- **WHEN** user declines hooks
- **THEN** `answers.install_hooks` SHALL be `False`

#### Scenario: Hooks installed during init
- **WHEN** `answers.install_hooks` is `True` and init proceeds
- **THEN** `install_post_commit_hook()` and `install_pre_commit_hook()` SHALL be called during the init process

#### Scenario: Defaults mode accepts hooks
- **WHEN** `run_wizard(use_defaults=True)` is called
- **THEN** `answers.install_hooks` SHALL be `False` (conservative default for unattended mode)

### Requirement: Post-init update offer
After init completes successfully, the system SHALL prompt the user to run `lexictl update` with `rich.prompt.Confirm` defaulting to `False`. If accepted, the update pipeline SHALL be invoked.

#### Scenario: Update declined (default)
- **WHEN** user accepts the default (No) at the update prompt
- **THEN** the system SHALL print guidance that `lexictl update` can be run later

#### Scenario: Update accepted
- **WHEN** user accepts the update offer
- **THEN** the update pipeline SHALL be invoked for the project

#### Scenario: Defaults mode skips update
- **WHEN** `run_wizard(use_defaults=True)` is called
- **THEN** the update offer SHALL NOT be shown
