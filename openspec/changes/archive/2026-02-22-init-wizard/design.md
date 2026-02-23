## Context

`lexictl init` currently calls `create_lexibrary_skeleton()` which writes a static config template and directory structure. Users must manually configure LLM provider, scope root, and agent environment after init. There is no project auto-detection, no agent environment awareness, and no guided setup flow.

Phase 8a (CLI Split) is a prerequisite — it moves `init` from the monolithic `lexi` CLI to the `lexictl` control plane. This design assumes 8a is complete: `lexictl` exists as a separate entry point, shared helpers live in `cli/_shared.py`, and the init command lives on `lexictl_app.py`.

The config schema currently has `LexibraryConfig` with nested sub-models for LLM, token budgets, mapping, ignore, daemon, crawl, and AST. It lacks `project_name`, `agent_environment`, and IWH configuration.

## Goals / Non-Goals

**Goals:**
- Replace static init with guided 8-step wizard that produces a customised config
- Auto-detect project properties (name, type, scope roots, agent environments, LLM providers)
- Persist agent environment selection in config for `lexictl setup --update`
- Add `IWHConfig` to schema for Phase 8c consumption
- Support non-interactive mode (`--defaults`) for CI/scripting
- Guard against re-init on existing projects

**Non-Goals:**
- Generate actual agent rules files (Phase 8c)
- Create or manage `.iwh` files (Phase 8c)
- Modify existing `CLAUDE.md` / `AGENTS.md` content (Phase 8c)
- Remove `HANDOFF.md` from existing projects (wizard simply doesn't create it for new projects)
- Remove or change `create_lexibrary_skeleton()` (preserved for backward compatibility)

## Decisions

### D1: Detection functions as pure utilities

Detection functions live in a new `src/lexibrary/init/detection.py` module as pure functions that take `project_root: Path` and return typed results. No stdout I/O, no Rich output — fully testable with `tmp_path`.

**Alternative considered:** Inline detection in wizard steps. Rejected because it makes testing harder and prevents reuse from `lexictl setup --update`.

### D2: `WizardAnswers` dataclass as data contract

The wizard collects all answers into a `WizardAnswers` dataclass. The scaffolder consumes this dataclass to generate the skeleton. This decouples the interactive flow from the filesystem operations.

**Alternative considered:** Direct config mutation during wizard steps. Rejected because it complicates cancellation (user says "no" at summary) and makes testing harder.

### D3: `rich.prompt` for interactive input

Use `rich.prompt.Prompt` and `rich.prompt.Confirm` for all user interaction. These integrate with Rich console output and are mockable in tests.

**Alternative considered:** `typer.prompt()` — rejected because it bypasses Rich console styling. `input()` — rejected because it's harder to mock and has no Rich integration.

### D4: Dynamic config generation with validation

`_generate_config_yaml()` builds a Python dict from `WizardAnswers`, validates it through `LexibraryConfig.model_validate()`, then serializes with `yaml.dump(sort_keys=False)`. Validation before write catches schema mismatches early.

**Alternative considered:** String templating. Rejected because it bypasses Pydantic validation and is fragile.

### D5: `tomllib` for pyproject.toml detection

Use stdlib `tomllib` (Python 3.11+) for reading `pyproject.toml` during project name detection. Project already requires Python 3.11+, so no new dependency needed.

### D6: Wizard-based scaffolder is additive

`create_lexibrary_from_wizard()` is a new function alongside `create_lexibrary_skeleton()`. The original function is preserved unchanged. The wizard path creates fewer files (no HANDOFF.md per D-053) and generates config dynamically.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Interactive prompts hard to test | `--defaults` mode for integration tests; mock `rich.prompt` for unit tests. Wizard steps are also individually testable functions. |
| `rich.prompt` incompatible with `CliRunner` | Wizard tests call `run_wizard()` directly, not through CLI. CLI tests use `--defaults`. |
| Non-TTY environments (CI, pipes) hang on prompt | Detect `sys.stdin.isatty()`; require `--defaults` when non-interactive. |
| Config template drift | Dynamic generation from `WizardAnswers` → Pydantic validation → YAML. No static template to maintain for wizard path. |
| Phase 8a not complete | This change explicitly depends on Phase 8a (cli-split). Implementation must wait for 8a. |
| Re-init on existing project could lose config | Re-init guard: error and point to `lexictl setup --update`. No destructive action. |

## Module Layout

```
src/lexibrary/
  config/
    schema.py          # + IWHConfig, project_name, agent_environment, iwh
    defaults.py        # + new sections in DEFAULT_PROJECT_CONFIG_TEMPLATE
    __init__.py        # + IWHConfig re-export
  init/
    __init__.py        # + create_lexibrary_from_wizard export
    detection.py       # NEW: pure detection functions
    wizard.py          # NEW: WizardAnswers, run_wizard(), step functions
    scaffolder.py      # + create_lexibrary_from_wizard(), _generate_config_yaml()
  cli/
    lexictl_app.py     # Replace init command, add setup --update stub
```

## Open Questions

None — all decisions are settled via D-054, D-055, D-058 in the decision log.
