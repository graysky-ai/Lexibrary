# init/wizard

**Summary:** Interactive 8-step init wizard for guided project setup using `rich.prompt`. Collects configuration into a `WizardAnswers` dataclass that decouples the interactive flow from filesystem operations.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `WizardAnswers` | `@dataclass` | Data contract holding all wizard outputs: `project_name`, `scope_root`, `agent_environments`, `llm_provider`, `llm_model`, `llm_api_key_env`, `llm_api_key_source: str = "env"`, `llm_api_key_value: str = ""`, `ignore_patterns`, `token_budgets_customized`, `token_budgets`, `iwh_enabled`, `confirmed` |
| `run_wizard` | `(project_root: Path, console: Console, *, use_defaults: bool = False) -> WizardAnswers \| None` | Run the 8-step wizard; returns `WizardAnswers` with `confirmed=True` on success, `None` if cancelled |

## Dependencies

- `lexibrary.init.detection` -- all detection functions for auto-discovery
- `dotenv` (`python-dotenv`) -- `set_key()` for writing API keys to `.env` files in dotenv mode
- `rich.console.Console` -- output rendering
- `rich.prompt.Prompt`, `rich.prompt.Confirm` -- interactive prompts
- `rich.table.Table` -- summary display in step 8

## Dependents

- `lexibrary.cli.lexictl_app` -- `init` command calls `run_wizard()`
- `lexibrary.init.scaffolder` -- consumes `WizardAnswers` in `create_lexibrary_from_wizard()`

## Key Concepts

- 8 steps: project name, scope root, agent environment (with missing-directory prompt), LLM provider (with API key storage sub-step), ignore patterns, token budgets, IWH toggle, summary/confirm
- Step 3 (`_step_agent_environment`) checks for missing base directories after selection via `check_missing_agent_dirs()`; in interactive mode, prompts the user to create them — declining removes those environments from the selection; in `use_defaults` mode, auto-accepts creation
- `use_defaults=True` skips all interactive prompts and accepts detected/default values (for CI/scripting via `--defaults`); defaults to `llm_api_key_source = "env"` without prompting or writing any files
- Each step is a private `_step_*` function that takes `console` and `use_defaults` keyword arg
- Step 4 (`_step_llm_provider`) includes an API key storage sub-step after provider selection, offering three modes:
  - `env` -- key is already set in the shell environment
  - `dotenv` -- prompts for the key value (password mode), writes it to `.env` via `dotenv.set_key()`, and appends `.env` to `.gitignore` if not already present
  - `manual` -- user will manage the key themselves
- `_write_dotenv_key` is a private helper that writes the API key to `.env` and ensures `.env` is in `.gitignore`
- Step 8 summary table shows `[stored in .env]`, `[from environment]`, or `[manual]` for the API key storage mode -- never the raw key value
- The `WizardAnswers` dataclass is a pure data contract -- it never touches the filesystem (except when `_write_dotenv_key` is called during step 4 for dotenv mode)
- Cancellation at the summary step returns `None` instead of raising

## Dragons

- `_step_llm_provider` returns a 5-tuple `(provider, model, api_key_env, api_key_source, api_key_value)` that gets unpacked into separate `WizardAnswers` fields
- `WizardAnswers.llm_api_key_value` is only populated when `api_key_source == "dotenv"` and is empty string `""` in all other modes
- `_write_dotenv_key` creates or appends to `.gitignore` -- it is the only wizard function with filesystem side-effects outside of `.lexibrary/`
- Token budget customization stores only the *changed* values in `WizardAnswers.token_budgets` (not the full set)
