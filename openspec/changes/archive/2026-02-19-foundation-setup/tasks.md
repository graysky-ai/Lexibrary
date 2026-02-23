## 1. Project Scaffolding

- [x] 1.1 Add `PyYAML>=6.0.0,<7.0.0` to `pyproject.toml` dependencies and run `uv sync`
- [x] 1.2 Create `src/lexibrary/artifacts/` package directory with `__init__.py`
- [x] 1.3 Create `src/lexibrary/exceptions.py` with `LexibraryNotFoundError`
- [x] 1.4 Remove `src/lexibrary/indexer/` module (retire v1 indexer)
- [x] 1.5 Update `.gitignore` — add `.lexibrary/START_HERE.md`, `.lexibrary/HANDOFF.md`, `.lexibrary/**/*.md`, `.lexibrary/**/.aindex`; ensure `.lexibrary/config.yaml` is NOT ignored

## 2. Artifact Data Models

- [x] 2.1 Create `src/lexibrary/artifacts/design_file.py` — `StalenessMetadata`, `DesignFile` Pydantic 2 models
- [x] 2.2 Create `src/lexibrary/artifacts/aindex.py` — `AIndexEntry`, `AIndexFile` Pydantic 2 models
- [x] 2.3 Create `src/lexibrary/artifacts/concept.py` — `ConceptFile` Pydantic 2 model
- [x] 2.4 Create `src/lexibrary/artifacts/guardrail.py` — `GuardrailThread` Pydantic 2 model with `GuardrailStatus` Literal type
- [x] 2.5 Update `src/lexibrary/artifacts/__init__.py` to re-export all five public models

## 3. Config System Rewrite

- [x] 3.1 Rewrite `src/lexibrary/config/schema.py` — new `LLMConfig`, `TokenBudgetConfig`, `MappingConfig`, `IgnoreConfig`, `DaemonConfig`, `LexibraryConfig` with `extra="ignore"` and v2 defaults
- [x] 3.2 Rewrite `src/lexibrary/config/loader.py` — `load_config()` with two-tier YAML merge (global XDG + project `.lexibrary/config.yaml`)
- [x] 3.3 Add `DEFAULT_PROJECT_CONFIG_TEMPLATE` YAML string (all sections with inline comments) to config module
- [x] 3.4 Remove `CrawlConfig` and all TOML-related imports from config module

## 4. Project Root Resolution

- [x] 4.1 Create `src/lexibrary/utils/root.py` — `find_project_root(start: Path) -> Path` with walk-up logic
- [x] 4.2 Wire `LexibraryNotFoundError` from `exceptions.py` into `find_project_root()`

## 5. Output Structure Helpers

- [x] 5.1 Create `src/lexibrary/utils/paths.py` — `mirror_path(project_root, source_file) -> Path` and `aindex_path(project_root, directory) -> Path` for mirror tree path construction
- [x] 5.2 Create `src/lexibrary/init/scaffolder.py` — `create_lexibrary_skeleton(project_root: Path)` that creates the `.lexibrary/` directory structure with placeholder files

## 6. CLI Rewrite

- [x] 6.1 Rewrite `src/lexibrary/cli.py` — register all v2 commands (`init`, `lookup`, `index`, `concepts`, `guardrails`, `guardrail new`, `search`, `update`, `validate`, `status`, `setup`, `daemon`) with correct help text
- [x] 6.2 Implement `lexi init` fully — call `create_lexibrary_skeleton()`, accept `--agent` flag (stub note about `lexi setup`), handle idempotent re-run
- [x] 6.3 All non-`init` commands: print stub message via `rich.console.Console` and exit cleanly
- [x] 6.4 All commands that require a project root: call `find_project_root()` and catch `LexibraryNotFoundError` → print friendly error and `raise typer.Exit(1)`

## 7. Tests

- [x] 7.1 Write tests for `StalenessMetadata`, `DesignFile`, `AIndexFile`, `ConceptFile`, `GuardrailThread` — validation, defaults, rejection of invalid input
- [x] 7.2 Write tests for `find_project_root()` — found in CWD, found in parent, not found raises `LexibraryNotFoundError`, stops at filesystem root
- [x] 7.3 Write tests for `mirror_path()` and `aindex_path()` — correct path construction for nested paths
- [x] 7.4 Write tests for two-tier config loading — global only, project only, merge with project override, partial project config, extra fields ignored
- [x] 7.5 Write CLI tests using `typer.testing.CliRunner` — `lexi init` creates skeleton, all stub commands exit 0 with stub message, commands without `.lexibrary/` exit 1 with friendly error
- [x] 7.6 Run `uv run pytest --cov=lexibrary` and confirm all tests pass; run `uv run ruff check src/ tests/` and `uv run mypy src/` and fix any issues
