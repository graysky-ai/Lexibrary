## Why

`lexictl init` currently calls `create_lexibrary_skeleton()` which creates a static directory skeleton with a template config. Users must manually edit config afterwards. There's no project detection, no agent environment setup, and no guided configuration — making first-time setup error-prone and disconnected from the project's actual properties. Phase 8b replaces this with an 8-step guided wizard that auto-detects project properties, configures agent environments, and produces a customised config in a single flow.

## What Changes

- **New interactive init wizard** — 8-step guided flow: project name detection, scope root, agent environment detection, LLM provider detection, ignore patterns, token budgets, IWH toggle, summary confirmation. Supports `--defaults` for non-interactive/CI use.
- **New detection functions** — pure utility functions that auto-detect project name (from pyproject.toml/package.json/directory), scope roots, agent environments (.claude/, .cursor/, AGENTS.md), LLM providers (from env vars), project type, and ignore pattern suggestions.
- **Config schema additions** — `IWHConfig` sub-model, `project_name`, `agent_environment` fields on `LexibraryConfig`.
- **Wizard-based scaffolder** — new `create_lexibrary_from_wizard()` that generates config.yaml dynamically from wizard answers instead of using the static template. Does NOT create `HANDOFF.md` (per D-053).
- **Re-init guard** — `lexictl init` on an already-initialised project errors and points to `lexictl setup --update`.
- **`lexictl setup --update` stub** — reads persisted `agent_environment` from config; actual rule generation deferred to Phase 8c.
- **Non-TTY detection** — requires `--defaults` when `stdin` is not a TTY.

## Capabilities

### New Capabilities
- `project-detection`: Pure functions for auto-detecting project name, scope roots, agent environments, LLM providers, project type, and ignore patterns from the filesystem and environment variables.
- `init-wizard`: Interactive 8-step wizard orchestrating detection, user prompts, and config assembly. Produces `WizardAnswers` dataclass consumed by the scaffolder.
- `setup-update`: `lexictl setup --update` command that reads persisted agent environment from config and refreshes agent rules (stub in 8b, implemented in 8c).

### Modified Capabilities
- `config-system`: Add `IWHConfig` sub-model (`enabled: bool`), `project_name: str`, and `agent_environment: list[str]` to `LexibraryConfig`. Update default config template.
- `project-scaffolding`: Add `create_lexibrary_from_wizard()` and `_generate_config_yaml()` that dynamically produce config.yaml from wizard answers. Wizard path does not create HANDOFF.md.
- `cli-commands`: Replace simple `lexictl init` with wizard-based init (re-init guard, `--defaults` flag, non-TTY detection). Add `lexictl setup --update` stub.

## Impact

- **Phase dependency:** Requires Phase 8a (CLI Split) to be complete — `init` and `setup` must live on `lexictl`, not `lexi`.
- **New files:** `src/lexibrary/init/detection.py`, `src/lexibrary/init/wizard.py`, `tests/test_init/test_detection.py`, `tests/test_init/test_wizard.py`
- **Modified files:** `config/schema.py`, `config/defaults.py`, `config/__init__.py`, `init/__init__.py`, `init/scaffolder.py`, `cli/lexictl_app.py` (post-8a path), `tests/test_config/test_schema.py`, `tests/test_init/test_scaffolder.py`, `tests/test_cli/test_lexictl.py`
- **New dependencies:** None — uses `tomllib` (stdlib 3.11+), `rich.prompt` (already in rich dependency).
- **Backward compatibility:** All new config fields have defaults; `extra="ignore"` ensures existing configs load without changes. `create_lexibrary_skeleton()` preserved unchanged.
- **Decisions referenced:** D-054 (combined wizard), D-055 (API key security), D-058 (persist agent environment).
