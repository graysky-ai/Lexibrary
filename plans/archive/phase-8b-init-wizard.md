# Phase 8b — Init Wizard + Setup

**Reference:** `plans/v2-master-plan.md` (Phase 8b section), `lexibrary-overview.md` (section 8)
**Depends on:** Phase 8a (CLI Split) — `init` must live on `lexictl`, not `lexi`
**Consumed by:** Phase 8c (Agent Rules + IWH)

---

## Goal

Replace the current simple `lexictl init` (which just creates a directory skeleton via `create_lexibrary_skeleton()`) with a guided 8-step wizard that combines project initialisation AND agent environment detection. Also implement `lexictl setup --update` for refreshing agent rules without re-running the full wizard.

---

## Decisions Referenced

| # | Decision | Summary |
|---|----------|---------|
| D-054 | Combined init+setup wizard | `lexictl init` replaces separate init + setup. Single guided flow. |
| D-055 | API key security model | Store provider name + env var name in config, never the key value. |
| D-058 | Persist agent environment in config | `agent_environment` field stored in project config. `lexictl setup --update` reads from config. |

---

## Pre-Requisite: Phase 8a (CLI Split)

This plan assumes Phase 8a is complete. After 8a:

- `lexictl` is a separate entry point registered in `pyproject.toml`
- `init` command lives on the `lexictl` Typer app in `src/lexibrary/cli/lexictl_app.py`
- Both CLIs share the same underlying modules
- Shared helpers (`console`, `require_project_root`) live in `src/lexibrary/cli/_shared.py`

---

## Sub-Phases

| Sub-Phase | Name | Depends On | Can Parallel With |
|-----------|------|------------|-------------------|
| **8b-1** | Config Schema Additions | — | 8b-2 (partially) |
| **8b-2** | Detection Functions | — | 8b-1 |
| **8b-3** | Wizard Module | 8b-1, 8b-2 | — |
| **8b-4** | Scaffolder Integration | 8b-3 | 8b-5 |
| **8b-5** | `lexictl setup --update` Stub | 8b-1 | 8b-4 |
| **8b-6** | CLI Registration + Re-init Guard | 8b-3, 8b-4 | — |
| **8b-7** | Tests | All above | — |

**Critical path:** 8b-1 + 8b-2 → 8b-3 → 8b-4 → 8b-6

---

## 8b-1 — Config Schema Additions

### New model: `IWHConfig`

Add to `src/lexibrary/config/schema.py`:

```python
class IWHConfig(BaseModel):
    """I Was Here ephemeral signal configuration."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
```

### New fields on `LexibraryConfig`

```python
class LexibraryConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_name: str = ""
    scope_root: str = "."
    agent_environment: list[str] = Field(default_factory=list)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    token_budgets: TokenBudgetConfig = Field(default_factory=TokenBudgetConfig)
    mapping: MappingConfig = Field(default_factory=MappingConfig)
    ignore: IgnoreConfig = Field(default_factory=IgnoreConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)
    ast: ASTConfig = Field(default_factory=ASTConfig)
    iwh: IWHConfig = Field(default_factory=IWHConfig)
```

### Update `DEFAULT_PROJECT_CONFIG_TEMPLATE`

Add new sections after `scope_root`:

```yaml
# Project name (auto-detected or set during lexictl init)
project_name: ""

# Agent environments configured by lexictl init (e.g., claude, cursor, codex)
agent_environment: []

# I Was Here (IWH) ephemeral inter-agent signals
iwh:
  enabled: true
```

### Backward compatibility

All new fields have defaults. `extra="ignore"` on all models ensures unknown keys are tolerated. Existing `config.yaml` files load correctly.

---

## 8b-2 — Detection Functions

### New module: `src/lexibrary/init/detection.py`

Pure functions for auto-detecting project properties. Each takes a `project_root: Path` and returns detected values. No I/O to stdout — testable utility functions.

```python
"""Project property detection for the init wizard."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


class DetectedProject(NamedTuple):
    name: str
    source: str  # "pyproject.toml", "package.json", or "directory"


class DetectedLLMProvider(NamedTuple):
    provider: str       # e.g., "anthropic", "openai"
    api_key_env: str    # e.g., "ANTHROPIC_API_KEY"
    model: str          # default model for that provider
```

### Detection functions

**`detect_project_name(project_root) -> DetectedProject`**
- Read `pyproject.toml` using `tomllib` (stdlib 3.11+). Parse `[project].name`.
- If not found, read `package.json` using `json`. Parse `name` key.
- Fallback: `project_root.name` (directory name).

**`detect_scope_roots(project_root) -> list[str]`**
- Check for `src/`, `lib/`, `app/` directories.
- Return list of those that exist (e.g., `["src/"]`).

**`detect_agent_environments(project_root) -> list[str]`**
- `.claude/` directory or `CLAUDE.md` file → "claude"
- `.cursor/` directory → "cursor"
- `AGENTS.md` file → "codex"
- Return deduplicated list.

**`check_existing_agent_rules(project_root, environment) -> str | None`**
- Grep for `<!-- lexibrary:` marker in the relevant rules file.
- Return the file path if found, None otherwise.

**`detect_llm_providers() -> list[DetectedLLMProvider]`**
- Check `os.environ.get()` for: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_HOST`.
- Return list of all found, in priority order.

**`detect_project_type(project_root) -> str | None`**
- `pyproject.toml`/`setup.py` → "python"
- `package.json` + `tsconfig.json` → "typescript"
- `package.json` → "node"
- `Cargo.toml` → "rust"
- `go.mod` → "go"

**`suggest_ignore_patterns(project_type) -> list[str]`**
- Python: `["**/migrations/", "**/__generated__/"]`
- Node/TypeScript: `["dist/", "build/", "coverage/", ".next/"]`
- Rust: `["target/"]`
- Go: `["vendor/"]`

---

## 8b-3 — Wizard Module

### New module: `src/lexibrary/init/wizard.py`

Orchestrates the 8 steps, collecting answers into a `WizardAnswers` dataclass.

```python
@dataclass
class WizardAnswers:
    project_name: str = ""
    scope_root: str = "."
    agent_environments: list[str] = field(default_factory=list)
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key_env: str = "ANTHROPIC_API_KEY"
    ignore_patterns: list[str] = field(default_factory=list)
    token_budgets_customized: bool = False
    token_budgets: dict[str, int] = field(default_factory=dict)
    iwh_enabled: bool = True
    confirmed: bool = False
```

### Main function

```python
def run_wizard(
    project_root: Path,
    console: Console,
    *,
    use_defaults: bool = False,
) -> WizardAnswers | None:
    """Run the interactive init wizard.

    Returns WizardAnswers if user confirmed, None if cancelled.
    """
```

### Interactive prompting approach

Use `rich.prompt.Prompt` and `rich.prompt.Confirm` for interactive input. These are mockable in tests and integrate well with Rich console output. Do NOT use `typer.prompt()` or bare `input()`.

### Step functions

Each step follows the same pattern:
1. Run detection
2. Display what was detected
3. If `use_defaults`, accept detection/default and return
4. Prompt user for confirmation or override
5. Return the answer

**Step 1 — Project Name:** Detect from `pyproject.toml` → `package.json` → directory name. Prompt for confirmation.

**Step 2 — Scope Root:** Detect `src/`, `lib/`, `app/`. Prompt for override. Show "Modify later" hint.

**Step 3 — Agent Environment:** Auto-detect from existing files/directories. Multi-select via comma-separated input. Check for existing Lexibrary sections. Ask before creating missing agent directories.

**Step 4 — LLM Provider:** Detect from env vars. Display transparency message: "We never store, log, or transmit your API key." Store provider + env var name. If no env var found, advise what to set.

**Step 5 — Ignore Patterns:** Detect project type, suggest patterns. Accept or override.

**Step 6 — Token Budgets:** Show defaults, offer to customize individual values.

**Step 7 — I Was Here:** Brief explanation. Enable/disable toggle.

**Step 8 — Summary + Confirm:** Display all answers in a table. Confirm.

---

## 8b-4 — Scaffolder Integration

### New function in `src/lexibrary/init/scaffolder.py`

```python
def create_lexibrary_from_wizard(
    project_root: Path,
    answers: WizardAnswers,
) -> list[Path]:
    """Create .lexibrary/ skeleton using wizard answers.

    Generates config.yaml dynamically from answers instead of
    using the static template.
    """
```

### Dynamic config generation

```python
def _generate_config_yaml(answers: WizardAnswers) -> str:
    """Generate config.yaml content from wizard answers."""
    config_dict = {
        "project_name": answers.project_name,
        "scope_root": answers.scope_root,
        "agent_environment": answers.agent_environments,
        "llm": {
            "provider": answers.llm_provider,
            "model": answers.llm_model,
            "api_key_env": answers.llm_api_key_env,
            "max_retries": 3,
            "timeout": 60,
        },
        "iwh": {"enabled": answers.iwh_enabled},
    }

    if answers.token_budgets_customized and answers.token_budgets:
        config_dict["token_budgets"] = answers.token_budgets

    # Validate before writing
    from lexibrary.config.schema import LexibraryConfig
    LexibraryConfig.model_validate(config_dict)

    header = (
        "# Lexibrary project configuration\n"
        "# Generated by `lexictl init`\n\n"
    )
    return header + yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
```

### HANDOFF.md removal

Per D-053, wizard-based scaffolder does NOT create `HANDOFF.md`. Creates:
- `.lexibrary/`, `.lexibrary/concepts/`, `.lexibrary/stack/`
- `.gitkeep` files for empty directories
- `config.yaml` from wizard answers
- `START_HERE.md` placeholder
- `.lexignore` with wizard patterns

---

## 8b-5 — `lexictl setup --update` Stub

In `src/lexibrary/cli/lexictl_app.py`:

```python
@app.command()
def setup(
    *,
    update_flag: Annotated[
        bool,
        typer.Option("--update", help="Refresh agent environment rules from config."),
    ] = False,
) -> None:
    """Manage agent environment rules."""
    if not update_flag:
        console.print(
            "[yellow]Usage:[/yellow] lexictl setup --update\n"
            "Run [cyan]lexictl init[/cyan] for first-time setup."
        )
        raise typer.Exit(0)

    project_root = require_project_root()
    config = load_config(project_root)

    if not config.agent_environment:
        console.print(
            "[yellow]No agent environments configured.[/yellow]\n"
            "Run [cyan]lexictl init[/cyan] to configure."
        )
        raise typer.Exit(1)

    # Phase 8c implements actual rule generation
    for env in config.agent_environment:
        console.print(f"  [dim]{env}: rule generation not yet implemented (Phase 8c)[/dim]")
```

---

## 8b-6 — CLI Registration + Re-init Guard

### Re-init guard in `lexictl init`

```python
@app.command()
def init(
    *,
    defaults: Annotated[
        bool,
        typer.Option("--defaults", help="Accept all defaults without prompting (for CI/scripting)."),
    ] = False,
) -> None:
    """Initialize Lexibrary in a project with a guided setup wizard."""
    project_root = Path.cwd()
    lexibrary_dir = project_root / ".lexibrary"

    # Re-init guard
    if lexibrary_dir.is_dir():
        console.print(
            "[red]Project already initialised.[/red]\n"
            "Use [cyan]lexictl setup --update[/cyan] to refresh agent rules."
        )
        raise typer.Exit(1)

    # Non-TTY detection
    if not sys.stdin.isatty() and not defaults:
        console.print(
            "[yellow]Non-interactive terminal detected.[/yellow] "
            "Use [cyan]lexictl init --defaults[/cyan] for non-interactive mode."
        )
        raise typer.Exit(1)

    # Run wizard
    answers = run_wizard(project_root, console, use_defaults=defaults)
    if answers is None:
        raise typer.Exit(1)

    # Create skeleton
    created = create_lexibrary_from_wizard(project_root, answers)

    console.print(
        f"\n[green]Lexibrary initialised.[/green] ({len(created)} items created)"
    )
    console.print("Next: Run [cyan]lexictl update[/cyan] to generate design files.")
```

---

## 8b-7 — Test Strategy

### Test file layout

```
tests/test_init/
    __init__.py           # already exists
    test_scaffolder.py    # already exists; add tests for create_lexibrary_from_wizard
    test_detection.py     # NEW: unit tests for all detection functions
    test_wizard.py        # NEW: unit tests for wizard steps + integration tests
```

### `test_detection.py`

Each detection function is a pure function testable with `tmp_path`:

- `TestDetectProjectName` — from pyproject.toml, package.json, directory name, precedence, malformed files
- `TestDetectScopeRoots` — detects src/, lib/, multiple, empty
- `TestDetectAgentEnvironments` — from .claude/, CLAUDE.md, .cursor/, AGENTS.md, no duplicates
- `TestDetectLLMProviders` — from env vars, priority order, empty when no vars (use `monkeypatch`)
- `TestDetectProjectType` — python, typescript, node, rust, go
- `TestSuggestIgnorePatterns` — per project type, None returns empty

### `test_wizard.py`

Testing interactive prompts requires mocking `rich.prompt.Prompt.ask` and `rich.prompt.Confirm.ask`:

- `TestWizardDefaults` — `run_wizard(use_defaults=True)` returns answers without prompting
- `TestWizardInteractive` — mock prompt responses, verify overrides work
- `TestWizardCancel` — user answering No at summary returns None
- `TestReInitGuard` — `lexictl init` on existing project errors, fresh project runs wizard

### Updated scaffolder tests

- `TestCreateFromWizard` — creates skeleton with answers, config contains wizard values, no HANDOFF.md, .lexignore includes wizard patterns

### Config schema tests

- `IWHConfig` defaults, `agent_environment` empty default, `project_name` empty default, `iwh.enabled` from YAML

---

## Files to Create

| File | Purpose |
|------|---------|
| `src/lexibrary/init/detection.py` | Detection functions for project name, scope root, agent environments, LLM providers, project type, ignore patterns |
| `src/lexibrary/init/wizard.py` | 8-step wizard: WizardAnswers, step functions, run_wizard |
| `tests/test_init/test_detection.py` | Unit tests for all detection functions |
| `tests/test_init/test_wizard.py` | Wizard step tests (mocked prompts) and integration tests |

## Files to Modify

| File | Change |
|------|--------|
| `src/lexibrary/config/schema.py` | Add `IWHConfig`, `agent_environment`, `project_name`, `iwh` to `LexibraryConfig` |
| `src/lexibrary/config/defaults.py` | Add new sections to `DEFAULT_PROJECT_CONFIG_TEMPLATE` |
| `src/lexibrary/config/__init__.py` | Re-export `IWHConfig` |
| `src/lexibrary/init/__init__.py` | Export `create_lexibrary_from_wizard` |
| `src/lexibrary/init/scaffolder.py` | Add `create_lexibrary_from_wizard()`, `_generate_config_yaml()`, `_generate_lexignore()` |
| `src/lexibrary/cli/lexictl_app.py` | Replace `init` with wizard, update `setup` with stub |
| `tests/test_config/test_schema.py` | Tests for new config fields |
| `tests/test_init/test_scaffolder.py` | Tests for `create_lexibrary_from_wizard` |
| `tests/test_cli/test_lexictl.py` | Tests for re-init guard, --defaults mode |

---

## Implementation Order

### Step 1: Config schema additions (8b-1)
1. Add `IWHConfig` to `config/schema.py`
2. Add `agent_environment`, `project_name`, `iwh` to `LexibraryConfig`
3. Update `config/__init__.py` re-exports
4. Update `DEFAULT_PROJECT_CONFIG_TEMPLATE`
5. Add schema tests
6. Run `uv run pytest tests/test_config/`

### Step 2: Detection functions (8b-2)
1. Create `init/detection.py`
2. Create `tests/test_init/test_detection.py`
3. Run `uv run pytest tests/test_init/test_detection.py`

### Step 3: Wizard module (8b-3)
1. Create `init/wizard.py`
2. Create `tests/test_init/test_wizard.py`
3. Run `uv run pytest tests/test_init/test_wizard.py`

### Step 4: Scaffolder integration (8b-4)
1. Add `create_lexibrary_from_wizard()` to `init/scaffolder.py`
2. Update `init/__init__.py` exports
3. Add scaffolder tests
4. Run `uv run pytest tests/test_init/`

### Step 5: CLI registration (8b-5 + 8b-6)
1. Update `lexictl init` with re-init guard, wizard, `--defaults`
2. Update `lexictl setup` with `--update` stub
3. Update CLI tests
4. Run full test suite

### Step 6: Quality checks
1. `uv run ruff check src/ tests/`
2. `uv run ruff format src/ tests/`
3. `uv run mypy src/`
4. `uv run pytest --cov=lexibrary`

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Interactive prompts hard to test | Use `--defaults` for integration tests; mock `rich.prompt` for unit tests |
| Config template becomes dynamic | Preserve `create_lexibrary_skeleton()` unchanged; new function is additive |
| Non-TTY environments | Detect `sys.stdin.isatty()`, require `--defaults` |
| `tomllib` availability | Project requires Python >=3.11 — safe to use |
| Rich prompt compatibility with CliRunner | Wizard tests use direct function calls; CLI tests use `--defaults` |

---

## What This Phase Does NOT Do

- **Generate agent rules** — Phase 8c writes actual rule files. 8b only detects and persists the environment selection.
- **Create `.iwh` files** — Phase 8c implements the IWH reader/writer. 8b only adds the `iwh.enabled` config toggle.
- **Modify existing CLAUDE.md/AGENTS.md** — The wizard detects and checks for markers, but content injection is Phase 8c.
- **Remove HANDOFF.md from existing projects** — Wizard-based init doesn't create it for new projects; existing projects are unaffected.

---

## What to Watch Out For

1. **API key security:** NEVER prompt for the actual key value. Detect env vars, store only the variable name. Show transparency message.
2. **`from __future__ import annotations`:** Every new module.
3. **Output via Rich Console only:** No bare `print()`.
4. **Config validation before write:** `_generate_config_yaml` validates through `LexibraryConfig.model_validate()` before writing.
5. **YAML serialization order:** Use `sort_keys=False` in `yaml.dump()`.
6. **Backward compatibility:** Keep `create_lexibrary_skeleton()` as-is. New function is additive.
7. **Rich prompt vs Typer prompt:** Use `rich.prompt.Prompt` and `rich.prompt.Confirm`, not `typer.prompt()`.
