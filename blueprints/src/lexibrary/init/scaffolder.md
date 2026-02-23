# init/scaffolder

**Summary:** Creates the `.lexibrary/` directory skeleton and `.lexignore` file idempotently -- never overwrites existing files. Supports both static template creation and wizard-driven dynamic generation. Ensures `.iwh` files and daemon runtime files (`.lexibrary.log`, `.lexibrary.pid`) are gitignored on every init.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `create_lexibrary_skeleton` | `(project_root: Path) -> list[Path]` | Create dirs (`concepts/`, `stack/`), `.gitkeep` files, template files (`config.yaml`, `START_HERE.md`), and `.lexignore`; call `ensure_iwh_gitignored()` and `_ensure_daemon_files_gitignored()`; return list of paths created |
| `create_lexibrary_from_wizard` | `(project_root: Path, answers: WizardAnswers) -> list[Path]` | Create skeleton using wizard answers; generates config dynamically; call `ensure_iwh_gitignored()` and `_ensure_daemon_files_gitignored()` |
| `_generate_config_yaml` | `(answers: WizardAnswers) -> str` | Build config YAML from wizard answers with Pydantic validation via `LexibraryConfig.model_validate()` |
| `_generate_lexignore` | `(patterns: list[str]) -> str` | Build `.lexignore` content starting with `LEXIGNORE_HEADER`, then `_DEFAULT_LEXIGNORE_PATTERNS` (`.env`, `.env.*`, `*.env`), then any wizard-collected patterns |
| `_ensure_daemon_files_gitignored` | `(project_root: Path) -> bool` | Append `.lexibrary/index.db` to `.gitignore` if not already present; creates `.gitignore` if it does not exist |
| `START_HERE_PLACEHOLDER` | `str` | Placeholder content for `START_HERE.md` before `lexictl update` runs; references IWH inter-agent signals |
| `_DEFAULT_LEXIGNORE_PATTERNS` | `list[str]` | Default `.lexignore` patterns always included: `.env`, `.env.*`, `*.env` -- prevents API keys in dotenv files from being indexed |
| `LEXIGNORE_HEADER` | `str` | Standard header comment block for `.lexignore` files |

## Dependencies

- `lexibrary.config.defaults` -- `DEFAULT_PROJECT_CONFIG_TEMPLATE`
- `lexibrary.config.schema` -- `LexibraryConfig` (for Pydantic validation of wizard config)
- `lexibrary.iwh.gitignore` -- `ensure_iwh_gitignored` (called during both init paths)
- `lexibrary.init.wizard` -- `WizardAnswers` (type only, `TYPE_CHECKING` guarded)
- `yaml` (PyYAML) -- config serialization

## Dependents

- `lexibrary.cli.lexictl_app` -- `init` command calls `create_lexibrary_from_wizard()`
- `lexibrary.init.__init__` -- re-exports `create_lexibrary_from_wizard`

## Key Concepts

- Idempotent: checks existence before creating each path; returns empty list if skeleton already exists
- `create_lexibrary_skeleton`: creates full skeleton with static `DEFAULT_PROJECT_CONFIG_TEMPLATE`
- `create_lexibrary_from_wizard`: creates skeleton with dynamically generated config from `WizardAnswers`
- `_generate_lexignore` always prepends `_DEFAULT_LEXIGNORE_PATTERNS` (`.env`, `.env.*`, `*.env`) before any wizard-collected patterns, deduplicating entries that appear in both lists
- `_generate_config_yaml` validates through Pydantic before serializing, so invalid wizard answers raise `ValidationError` before writing
- Both init paths call `ensure_iwh_gitignored()` to add `**/.iwh` to `.gitignore`
- Both init paths call `_ensure_daemon_files_gitignored()` to add `.lexibrary/index.db` to `.gitignore`
- `_DAEMON_GITIGNORE_PATTERNS` constant holds the list of generated artifacts (`.lexibrary/index.db`) to gitignore
- `START_HERE_PLACEHOLDER` references IWH signals, guiding agents to check for `.iwh` files
- HANDOFF.md has been removed -- IWH files replace the old HANDOFF mechanism

## Dragons

- `WizardAnswers` import is guarded by `TYPE_CHECKING` to avoid circular imports (wizard depends on detection, scaffolder is separate)
- Custom token budgets in `WizardAnswers` only contain changed values, not the full default set
