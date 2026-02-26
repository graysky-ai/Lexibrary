# project-scaffolding Specification

## Purpose
TBD - created by archiving change phase-1-foundation. Update Purpose after archive.
## Requirements
### Requirement: Project directory structure
The system SHALL have a Python package structure with source code under `src/lexibrary/` and test code under `tests/`. The CLI SHALL be a package at `src/lexibrary/cli/` (not a single file).

#### Scenario: CLI is a package directory
- **WHEN** inspecting `src/lexibrary/cli/`
- **THEN** it is a directory containing `__init__.py`, `_shared.py`, `lexi_app.py`, and `lexictl_app.py`

#### Scenario: No cli.py file exists
- **WHEN** inspecting `src/lexibrary/`
- **THEN** there is no `cli.py` file

### Requirement: Project metadata in pyproject.toml
The `[project.scripts]` section SHALL define two entry points: `lexi` mapping to `"lexibrary.cli:lexi_app"` and `lexictl` mapping to `"lexibrary.cli:lexictl_app"`. The `lexibrary` alias SHALL NOT exist.

#### Scenario: CLI entry points are configured
- **WHEN** reading `pyproject.toml` `[project.scripts]`
- **THEN** `lexi` maps to `"lexibrary.cli:lexi_app"` and `lexictl` maps to `"lexibrary.cli:lexictl_app"`

#### Scenario: No lexibrary alias exists
- **WHEN** reading `pyproject.toml` `[project.scripts]`
- **THEN** there is no `lexibrary` entry

### Requirement: Python version is pinned
The system SHALL require Python 3.11+ and pin to Python 3.12 via `.python-version` file.

#### Scenario: Python version file exists
- **WHEN** reading `.python-version`
- **THEN** it contains exactly "3.12"

### Requirement: .gitignore is configured
The system SHALL exclude Python artifacts, virtual environments, generated BAML code, and `.lexibrary/` generated artifacts while keeping `.lexibrary/config.yaml` tracked. The `.gitignore` SHALL include a `**/.iwh` pattern for IWH ephemeral files.

#### Scenario: .gitignore contains .lexibrary/ generated file patterns
- **WHEN** reading `.gitignore`
- **THEN** it includes patterns for `.lexibrary/START_HERE.md`, `.lexibrary/**/*.md`, `.lexibrary/**/.aindex`, `**/.iwh`, `baml_client/`, and standard Python patterns (`__pycache__/`, `*.pyc`, `.venv/`, `venv/`)

#### Scenario: .gitignore does NOT contain HANDOFF.md pattern
- **WHEN** reading `.gitignore` after Phase 8c changes
- **THEN** it SHALL NOT contain `.lexibrary/HANDOFF.md` pattern

#### Scenario: .lexibrary/config.yaml is NOT gitignored
- **WHEN** running `git status` in a project with `.lexibrary/config.yaml`
- **THEN** `config.yaml` is tracked (not in .gitignore), because project config is version-controlled

### Requirement: Module initialization
The `__main__.py` SHALL import and run `lexi_app` (the agent-facing CLI) when invoked via `python -m lexibrary`.

#### Scenario: Root module can be run as a script
- **WHEN** running `python -m lexibrary`
- **THEN** it runs the `lexi_app` (agent-facing CLI)

### Requirement: artifacts module structure
The system SHALL have `src/lexibrary/artifacts/` as a proper Python package with `__init__.py` re-exporting all public model classes.

#### Scenario: artifacts package is importable
- **WHEN** importing `from lexibrary.artifacts import DesignFile`
- **THEN** the import succeeds without error

#### Scenario: artifacts package has module files
- **WHEN** inspecting `src/lexibrary/artifacts/`
- **THEN** it contains `__init__.py`, `design_file.py`, `aindex.py`, and `concept.py` (guardrail.py removed)

#### Scenario: stack module exists
- **WHEN** inspecting `src/lexibrary/stack/`
- **THEN** it contains `__init__.py`, `models.py`, `parser.py`, `serializer.py`, `template.py`, `index.py`, and `mutations.py`

### Requirement: exceptions module
The system SHALL have `src/lexibrary/exceptions.py` containing all project-level exception classes, starting with `LexibraryNotFoundError`.

#### Scenario: exceptions module is importable
- **WHEN** importing `from lexibrary.exceptions import LexibraryNotFoundError`
- **THEN** the import succeeds without error

### Requirement: Stack directory in scaffolding
`lexictl init` SHALL create a `.lexibrary/stack/` directory, a `.lexibrary/concepts/` directory, and a `.lexibrary/conventions/` directory in the project skeleton. It SHALL NOT create a `HANDOFF.md` file.

#### Scenario: Init creates stack directory
- **WHEN** running `lexictl init` in an empty directory
- **THEN** `.lexibrary/stack/` SHALL be created

#### Scenario: Init creates conventions directory
- **WHEN** running `lexictl init` in an empty directory
- **THEN** `.lexibrary/conventions/` SHALL be created with a `.gitkeep` file

#### Scenario: Init does not create HANDOFF.md
- **WHEN** running `lexictl init` in an empty directory
- **THEN** `.lexibrary/HANDOFF.md` SHALL NOT be created

#### Scenario: Init creates IWH gitignore entry
- **WHEN** running `lexictl init` in an empty directory
- **THEN** `.gitignore` SHALL contain the `**/.iwh` pattern

### Requirement: Test directory structure
CLI tests SHALL be organized as a package at `tests/test_cli/` containing `__init__.py`, `test_lexi.py` (agent-facing command tests), and `test_lexictl.py` (maintenance command tests). The monolithic `tests/test_cli.py` file SHALL NOT exist.

#### Scenario: Test CLI package exists
- **WHEN** inspecting `tests/test_cli/`
- **THEN** it is a directory containing `__init__.py`, `test_lexi.py`, and `test_lexictl.py`

#### Scenario: Old test file does not exist
- **WHEN** inspecting `tests/`
- **THEN** there is no `test_cli.py` file

### Requirement: Wizard-based scaffolder
`create_lexibrary_from_wizard(project_root: Path, answers: WizardAnswers) -> list[Path]` SHALL create the `.lexibrary/` skeleton using wizard answers. It SHALL return a list of all created file paths.

The function SHALL create:
- `.lexibrary/` directory
- `.lexibrary/concepts/` directory with `.gitkeep`
- `.lexibrary/conventions/` directory with `.gitkeep`
- `.lexibrary/stack/` directory with `.gitkeep`
- `.lexibrary/config.yaml` generated dynamically from `answers`
- `.lexibrary/START_HERE.md` placeholder
- `.lexignore` with wizard-provided ignore patterns

The function SHALL NOT create `HANDOFF.md`.

#### Scenario: Creates directory structure
- **WHEN** `create_lexibrary_from_wizard()` is called with valid answers
- **THEN** `.lexibrary/`, `.lexibrary/concepts/`, `.lexibrary/conventions/`, and `.lexibrary/stack/` SHALL exist

#### Scenario: Creates config from answers
- **WHEN** answers has `project_name="my-app"` and `llm_provider="anthropic"`
- **THEN** `.lexibrary/config.yaml` SHALL contain `project_name: my-app` and `provider: anthropic`

#### Scenario: Does NOT create HANDOFF.md
- **WHEN** `create_lexibrary_from_wizard()` is called
- **THEN** `.lexibrary/HANDOFF.md` SHALL NOT exist

#### Scenario: Creates .lexignore with patterns
- **WHEN** answers has `ignore_patterns=["dist/", "build/"]`
- **THEN** `.lexignore` SHALL contain those patterns

#### Scenario: Creates .lexignore empty when no patterns
- **WHEN** answers has `ignore_patterns=[]`
- **THEN** `.lexignore` SHALL exist with a header comment but no patterns

#### Scenario: Returns list of created paths
- **WHEN** `create_lexibrary_from_wizard()` completes
- **THEN** the returned list SHALL contain all created file paths including the conventions directory gitkeep

### Requirement: Dynamic config generation
`_generate_config_yaml(answers: WizardAnswers) -> str` SHALL build a config dict from answers, validate it through `LexibraryConfig.model_validate()`, and serialize to YAML with `sort_keys=False`. The output SHALL include a header comment indicating it was generated by `lexictl init`.

#### Scenario: Generated config is valid
- **WHEN** `_generate_config_yaml()` is called with valid answers
- **THEN** the output SHALL be valid YAML that loads into a `LexibraryConfig` without errors

#### Scenario: Config includes all wizard fields
- **WHEN** answers has `project_name`, `scope_root`, `agent_environments`, LLM settings, and IWH setting
- **THEN** the generated YAML SHALL include all of these fields

#### Scenario: Custom token budgets included
- **WHEN** `answers.token_budgets_customized` is `True` and `answers.token_budgets` has values
- **THEN** the generated YAML SHALL include a `token_budgets` section with those values

#### Scenario: Default token budgets omitted
- **WHEN** `answers.token_budgets_customized` is `False`
- **THEN** the generated YAML SHALL NOT include a `token_budgets` section (defaults apply)

#### Scenario: Config validated before write
- **WHEN** `_generate_config_yaml()` is called with invalid data
- **THEN** a `ValidationError` SHALL be raised before any YAML output is produced

### Requirement: Lexignore generation
The scaffolder SHALL generate a `.lexignore` file with a header comment and any ignore patterns from the wizard answers, in gitignore format.

#### Scenario: Lexignore with patterns
- **WHEN** wizard answers include `ignore_patterns=["dist/", "coverage/"]`
- **THEN** `.lexignore` SHALL contain `dist/` and `coverage/` as patterns

#### Scenario: Lexignore with header
- **WHEN** `.lexignore` is generated
- **THEN** the file SHALL start with a comment header explaining its purpose

### Requirement: Original scaffolder preserved
`create_lexibrary_skeleton()` SHALL remain unchanged and continue to work as before. The wizard-based scaffolder is additive.

#### Scenario: Old scaffolder still works
- **WHEN** `create_lexibrary_skeleton(project_root)` is called
- **THEN** it SHALL create the same structure as before (including HANDOFF.md)

### Requirement: Wizard scaffolder exported from init package
`create_lexibrary_from_wizard` SHALL be importable from `lexibrary.init`.

#### Scenario: Import create_lexibrary_from_wizard
- **WHEN** running `from lexibrary.init import create_lexibrary_from_wizard`
- **THEN** the import SHALL succeed

