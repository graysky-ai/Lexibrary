## 1. Config Schema Additions

> **Depends on:** Nothing (can start immediately after Phase 8a)
> **Unlocks:** Groups 3, 4, 5

- [x] 1.1 Add `IWHConfig` model to `src/lexibrary/config/schema.py` with `enabled: bool = True` and `model_config = ConfigDict(extra="ignore")`
- [x] 1.2 Add `project_name: str = ""`, `agent_environment: list[str] = Field(default_factory=list)`, and `iwh: IWHConfig = Field(default_factory=IWHConfig)` to `LexibraryConfig`
- [x] 1.3 Re-export `IWHConfig` from `src/lexibrary/config/__init__.py`
- [x] 1.4 Add `project_name`, `agent_environment`, and `iwh` sections to `DEFAULT_PROJECT_CONFIG_TEMPLATE` in `src/lexibrary/config/defaults.py`
- [x] 1.5 Add tests for new config fields: `IWHConfig` defaults, `IWHConfig` extra ignored, `project_name` default, `agent_environment` default, `iwh.enabled` from YAML, `agent_environment` from YAML
- [x] 1.6 Run `uv run pytest tests/test_config/ -v` and verify all pass

## 2. Detection Functions

> **Depends on:** Nothing (can parallel with Group 1)
> **Unlocks:** Group 3

- [x] 2.1 Create `src/lexibrary/init/detection.py` with `DetectedProject` and `DetectedLLMProvider` named tuples
- [x] 2.2 Implement `detect_project_name()` — pyproject.toml → package.json → directory name precedence
- [x] 2.3 Implement `detect_scope_roots()` — check for src/, lib/, app/ directories
- [x] 2.4 Implement `detect_agent_environments()` — .claude/, CLAUDE.md, .cursor/, AGENTS.md markers
- [x] 2.5 Implement `check_existing_agent_rules()` — grep for `<!-- lexibrary:` marker in rules files
- [x] 2.6 Implement `detect_llm_providers()` — check env vars in priority order
- [x] 2.7 Implement `detect_project_type()` and `suggest_ignore_patterns()` — project type detection and pattern suggestions
- [x] 2.8 Create `tests/test_init/test_detection.py` with tests for all detection functions (use tmp_path and monkeypatch)
- [x] 2.9 Run `uv run pytest tests/test_init/test_detection.py -v` and verify all pass

## 3. Wizard Module

> **Depends on:** Groups 1, 2 (needs config schema + detection functions)
> **Unlocks:** Group 4

- [x] 3.1 Create `src/lexibrary/init/wizard.py` with `WizardAnswers` dataclass
- [x] 3.2 Implement step functions: `_step_project_name()`, `_step_scope_root()`, `_step_agent_environment()`, `_step_llm_provider()`, `_step_ignore_patterns()`, `_step_token_budgets()`, `_step_iwh()`, `_step_summary()`
- [x] 3.3 Implement `run_wizard()` orchestrator with `use_defaults` support
- [x] 3.4 Create `tests/test_init/test_wizard.py` — test `use_defaults=True` returns answers without prompting, mock `rich.prompt` for interactive tests, test cancellation returns `None`
- [x] 3.5 Run `uv run pytest tests/test_init/test_wizard.py -v` and verify all pass

## 4. Scaffolder Integration

> **Depends on:** Group 3 (needs WizardAnswers)
> **Unlocks:** Group 5

- [x] 4.1 Add `_generate_config_yaml(answers: WizardAnswers) -> str` to `src/lexibrary/init/scaffolder.py` — build dict, validate via LexibraryConfig.model_validate(), yaml.dump()
- [x] 4.2 Add `_generate_lexignore(patterns: list[str]) -> str` to scaffolder
- [x] 4.3 Add `create_lexibrary_from_wizard(project_root, answers) -> list[Path]` to scaffolder — create dirs, config, START_HERE.md, .lexignore, .gitkeep files, no HANDOFF.md
- [x] 4.4 Export `create_lexibrary_from_wizard` from `src/lexibrary/init/__init__.py`
- [x] 4.5 Add scaffolder tests: creates structure from answers, config contains wizard values, no HANDOFF.md, .lexignore has patterns, returned paths correct
- [x] 4.6 Run `uv run pytest tests/test_init/ -v` and verify all pass

## 5. CLI Registration + Setup Stub

> **Depends on:** Group 4 (needs wizard + scaffolder); also requires Phase 8a complete
> **Unlocks:** Group 6

- [x] 5.1 Replace `init` command in `src/lexibrary/cli/lexictl_app.py` — re-init guard, non-TTY detection, `--defaults` flag, wizard integration, creation summary
- [x] 5.2 Add `setup` command with `--update` flag — usage hint when no flag, load config, check agent_environment, stub iteration over environments
- [x] 5.3 Add CLI tests: re-init guard blocks existing project, `--defaults` creates skeleton, setup without --update shows usage, setup --update with empty env shows message
- [x] 5.4 Run `uv run pytest tests/test_cli/ -v` and verify all pass

## 6. Quality Checks + Blueprints

> **Depends on:** Groups 1–5

- [x] 6.1 Run `uv run ruff check src/ tests/` and fix any lint issues
- [x] 6.2 Run `uv run ruff format src/ tests/` and fix formatting
- [x] 6.3 Run `uv run mypy src/` and fix type errors
- [x] 6.4 Run `uv run pytest --cov=lexibrary` and verify full suite passes
- [x] 6.5 Update blueprints: create design files for `init/detection.py` and `init/wizard.py`; update design files for `config/schema.py`, `config/defaults.py`, `init/scaffolder.py`, `cli/lexictl_app.py`
