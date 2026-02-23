# init/wizard

**Summary:** Interactive 8-step init wizard for guided project setup using `rich.prompt`. Collects configuration into a `WizardAnswers` dataclass that decouples the interactive flow from filesystem operations.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `WizardAnswers` | `@dataclass` | Data contract holding all wizard outputs: `project_name`, `scope_root`, `agent_environments`, `llm_provider`, `llm_model`, `llm_api_key_env`, `ignore_patterns`, `token_budgets_customized`, `token_budgets`, `iwh_enabled`, `confirmed` |
| `run_wizard` | `(project_root: Path, console: Console, *, use_defaults: bool = False) -> WizardAnswers \| None` | Run the 8-step wizard; returns `WizardAnswers` with `confirmed=True` on success, `None` if cancelled |

## Dependencies

- `lexibrarian.init.detection` -- all detection functions for auto-discovery
- `rich.console.Console` -- output rendering
- `rich.prompt.Prompt`, `rich.prompt.Confirm` -- interactive prompts
- `rich.table.Table` -- summary display in step 8

## Dependents

- `lexibrarian.cli.lexictl_app` -- `init` command calls `run_wizard()`
- `lexibrarian.init.scaffolder` -- consumes `WizardAnswers` in `create_lexibrary_from_wizard()`

## Key Concepts

- 8 steps: project name, scope root, agent environment, LLM provider, ignore patterns, token budgets, IWH toggle, summary/confirm
- `use_defaults=True` skips all interactive prompts and accepts detected/default values (for CI/scripting via `--defaults`)
- Each step is a private `_step_*` function that takes `console` and `use_defaults` keyword arg
- The `WizardAnswers` dataclass is a pure data contract -- it never touches the filesystem
- Cancellation at the summary step returns `None` instead of raising

## Dragons

- `_step_llm_provider` returns a 3-tuple `(provider, model, api_key_env)` that gets unpacked into separate `WizardAnswers` fields
- Token budget customization stores only the *changed* values in `WizardAnswers.token_budgets` (not the full set)
