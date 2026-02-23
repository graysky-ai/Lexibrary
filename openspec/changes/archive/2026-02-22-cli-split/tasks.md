## 1. Create CLI Package Structure

- [x] 1.1 Create `src/lexibrary/cli/` directory
- [x] 1.2 Create `src/lexibrary/cli/__init__.py` with re-exports of `lexi_app` and `lexictl_app`
- [x] 1.3 Create `src/lexibrary/cli/_shared.py` with `console`, `require_project_root()`, and `stub()` extracted from current `cli.py`
- [x] 1.4 Create `src/lexibrary/cli/lexi_app.py` with agent-facing Typer app and commands: lookup, index, describe, concepts, concept (sub-group), stack (sub-group), search — plus stack helper functions
- [x] 1.5 Create `src/lexibrary/cli/lexictl_app.py` with maintenance Typer app and commands: init, update, validate, status, setup (stub), daemon (stub)
- [x] 1.6 Delete `src/lexibrary/cli.py`

## 2. Update Cross-References in Source Code

- [x] 2.1 Update `_shared.py` error message: `"lexi init"` → `"lexictl init"`
- [x] 2.2 Update `lexictl_app.py` init `--agent` help/output: `"lexi setup"` → `"lexictl setup"`
- [x] 2.3 Update `lexi_app.py` lookup messages: `"lexi update"` → `"lexictl update"` (two places: missing design file and stale design file)
- [x] 2.4 Update `lexi_app.py` concept_link message: `"lexi update"` → `"lexictl update"`
- [x] 2.5 Update `lexictl_app.py` status command: `"lexi validate"` → `"lexictl validate"` (four places) and `"lexi:"` → `"lexictl:"` prefix
- [x] 2.6 Update `lexictl_app.py` status dashboard: `"lexi validate"` → `"lexictl validate"`
- [x] 2.7 Update `src/lexibrary/validator/checks.py`: `"lexi update"` → `"lexictl update"`
- [x] 2.8 Update `src/lexibrary/init/scaffolder.py`: `"lexi update"` → `"lexictl update"`
- [x] 2.9 Update `src/lexibrary/config/defaults.py`: `"lexi init"` → `"lexictl init"`
- [x] 2.10 Update `src/lexibrary/daemon/service.py`: `"lexi daemon"` → `"lexictl daemon"`

## 3. Update Entry Points and Module Runner

- [x] 3.1 Update `pyproject.toml` `[project.scripts]`: set `lexi = "lexibrary.cli:lexi_app"`, `lexictl = "lexibrary.cli:lexictl_app"`, remove `lexibrary` alias
- [x] 3.2 Update `src/lexibrary/__main__.py` to import and run `lexi_app` instead of `app`
- [x] 3.3 Run `uv sync` to re-register entry points

## 4. Split and Update Tests

- [x] 4.1 Create `tests/test_cli/` directory with `__init__.py`
- [x] 4.2 Create `tests/test_cli/test_lexi.py` with agent-facing command tests (TestHelp for lexi, TestIndexCommand, TestLookupCommand, TestLookupConventionInheritance, TestDescribeCommand, TestConceptsCommand, TestConceptNewCommand, TestConceptLinkCommand, all TestStack*Command classes, TestUnifiedSearchCommand, TestNoProjectRoot for lexi)
- [x] 4.3 Create `tests/test_cli/test_lexictl.py` with maintenance command tests (TestHelp for lexictl, TestInit, TestUpdateCommand, TestValidateCommand, TestStatusCommand, TestStubCommands for setup/daemon, TestNoProjectRoot for lexictl)
- [x] 4.4 Update all test assertion strings: `"lexi init"` → `"lexictl init"`, `"lexi update"` → `"lexictl update"`, `"lexi validate"` → `"lexictl validate"`, `"lexi setup"` → `"lexictl setup"`
- [x] 4.5 Delete `tests/test_cli.py`
- [x] 4.6 Update `tests/test_validator/test_warning_checks.py`: `"lexi update"` → `"lexictl update"`
- [x] 4.7 Update `tests/test_validator/test_report.py`: `"lexi update"` → `"lexictl update"` if referenced

## 5. Update Blueprints

- [x] 5.1 Update `blueprints/START_HERE.md` to reflect `cli/` package structure in the topology tree
- [x] 5.2 Delete `blueprints/src/lexibrary/cli.md`
- [x] 5.3 Create `blueprints/src/lexibrary/cli/__init__.md` (package re-exports design file)
- [x] 5.4 Create `blueprints/src/lexibrary/cli/_shared.md` (shared helpers design file)
- [x] 5.5 Create `blueprints/src/lexibrary/cli/lexi_app.md` (agent-facing CLI design file)
- [x] 5.6 Create `blueprints/src/lexibrary/cli/lexictl_app.md` (maintenance CLI design file)

## 6. Verify

- [x] 6.1 Run `uv run pytest --cov=lexibrary` — all tests pass
- [x] 6.2 Run `uv run ruff check src/ tests/` — no lint issues
- [x] 6.3 Run `uv run ruff format src/ tests/` — formatting clean
- [x] 6.4 Run `uv run mypy src/` — type checks pass
- [x] 6.5 Smoke test: `uv run lexi --help` shows only agent commands
- [x] 6.6 Smoke test: `uv run lexictl --help` shows only maintenance commands
- [x] 6.7 Verify `lexi update` does NOT exist (Typer error)
- [x] 6.8 Verify `lexictl lookup` does NOT exist (Typer error)
