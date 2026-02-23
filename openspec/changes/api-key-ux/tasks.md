## 1. Dependency and Schema

- [x] 1.1 Add `python-dotenv>=1.0.0,<2.0.0` to `pyproject.toml` dependencies and run `uv sync` to update the lockfile
- [x] 1.2 Add `api_key_source: str = "env"` field to `LLMConfig` in `src/lexibrary/config/schema.py`
- [x] 1.3 Add `api_key_source: env` line (with comment) to `DEFAULT_PROJECT_CONFIG_TEMPLATE` in `src/lexibrary/config/defaults.py`

## 2. Default Ignore Patterns

- [x] 2.1 Add `.env`, `.env.*`, and `*.env` to `IgnoreConfig.additional_patterns` default list in `src/lexibrary/config/schema.py`
- [x] 2.2 Add the same three patterns to `additional_patterns` in `DEFAULT_PROJECT_CONFIG_TEMPLATE` in `src/lexibrary/config/defaults.py`

## 3. Scaffolder .lexignore Update

- [x] 3.1 Add `.env`, `.env.*`, and `*.env` to the patterns written to `.lexignore` by `create_lexibrary_skeleton()` in `src/lexibrary/init/scaffolder.py`

## 4. Wizard Step 4 Extension

- [x] 4.1 Add `llm_api_key_source: str = "env"` and `llm_api_key_value: str = ""` fields to `WizardAnswers` dataclass in `src/lexibrary/init/wizard.py`
- [x] 4.2 Extend `_step_llm_provider()` in `src/lexibrary/init/wizard.py` to add the storage-method sub-step prompt (`env` / `dotenv` / `manual`) after provider selection
- [x] 4.3 Implement `.env` write logic in the wizard: when `dotenv` is chosen, prompt for the key value (password mode), call `dotenv.set_key()` to write the key, append `.env` to `.gitignore` if not already present
- [x] 4.4 Update the Step 8 summary table in `_step_summary()` to show `[stored in .env]`, `[from environment]`, or `[manual]` for the API key — never the raw value
- [x] 4.5 Ensure `use_defaults=True` mode skips the storage sub-step and defaults to `llm_api_key_source = "env"` without prompting or writing any files

## 5. CLI Startup Dotenv Loading

- [x] 5.1 Add a startup callback to `src/lexibrary/cli/lexi_app.py` that reads raw YAML from the project config, checks `llm.api_key_source`, and calls `load_dotenv(project_root / ".env", override=False)` when it equals `"dotenv"`
- [x] 5.2 Apply the same startup callback to `src/lexibrary/cli/lexictl_app.py`
- [x] 5.3 Ensure both callbacks handle `find_project_root()` returning `None` and missing `.env` files silently without raising exceptions

## 6. Blueprint Updates

- [x] 6.1 Update `blueprints/src/lexibrary/config/schema.md` to document the new `api_key_source` field on `LLMConfig`
- [x] 6.2 Update `blueprints/src/lexibrary/init/wizard.md` to document the Step 4 storage sub-step and new `WizardAnswers` fields
- [x] 6.3 Update `blueprints/src/lexibrary/init/scaffolder.md` to note the `.env` patterns in `.lexignore`
- [x] 6.4 Update `blueprints/src/lexibrary/cli/lexi_app.md` and `blueprints/src/lexibrary/cli/lexictl_app.md` to note the dotenv startup hook

## 7. Tests

- [x] 7.1 Add tests for `LLMConfig.api_key_source` default and YAML loading in `tests/test_config/`
- [x] 7.2 Add tests for `.env` patterns in `IgnoreConfig.additional_patterns` defaults in `tests/test_ignore/`
- [x] 7.3 Add tests for scaffolder writing `.env` patterns to `.lexignore` in `tests/test_init/test_scaffolder.py`
- [x] 7.4 Add tests for wizard `_step_llm_provider()` with mock prompts covering all three storage modes in `tests/test_init/test_wizard.py`
- [x] 7.5 Add tests confirming `WizardAnswers.llm_api_key_value` is `""` in defaults mode and is populated only in dotenv mode
