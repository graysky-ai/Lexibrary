## 1. Serializer Annotation (D-070)

- [x] 1.1 Update `serialize_design_file()` in `src/lexibrarian/artifacts/design_file_serializer.py` to emit the annotation line `*(see \`lexi lookup\` for live reverse references)*` after the `## Dependents` heading, before the bullet items or `(none)`
- [x] 1.2 Add/update unit tests in `tests/` for `serialize_design_file()` verifying the annotation appears with empty dependents
- [x] 1.3 Add/update unit tests verifying the annotation appears alongside non-empty dependents
- [x] 1.4 Add a round-trip test: serialize a DesignFile with the annotation, then parse it back and confirm the annotation is not in the parsed `dependents` list
- [x] 1.5 Run `uv run pytest` to confirm all serializer and parser tests pass

## 2. Gitignore Hygiene

- [x] 2.1 Add `.lexibrary/index.db` pattern to the project `.gitignore`
- [x] 2.2 Update `_ensure_daemon_files_gitignored()` in `src/lexibrarian/init/scaffolder.py` (or create a dedicated helper) to include `.lexibrary/index.db` in the patterns ensured during `lexictl init`
- [x] 2.3 Add a test verifying that `create_lexibrary_skeleton()` results in `.lexibrary/index.db` being gitignored
- [x] 2.4 Add a test verifying that `create_lexibrary_from_wizard()` results in `.lexibrary/index.db` being gitignored

## 3. Linkgraph Blueprints

- [x] 3.1 Create `blueprints/src/lexibrarian/linkgraph/__init__.md` describing the module's public API re-exports
- [x] 3.2 Create `blueprints/src/lexibrarian/linkgraph/schema.md` describing DDL constants, `ensure_schema()`, `check_schema_version()`, `set_pragmas()`, `SCHEMA_VERSION`, and the 8-table + FTS5 structure
- [x] 3.3 Create `blueprints/src/lexibrarian/linkgraph/builder.md` describing the `IndexBuilder` class, `full_build()`, `incremental_update()`, and build pipeline
- [x] 3.4 Create `blueprints/src/lexibrarian/linkgraph/query.md` describing the `LinkGraph` read-only query interface, key methods, `traverse()`, and graceful degradation

## 4. START_HERE.md Updates

- [x] 4.1 Add `linkgraph/` entry to the project topology tree in `blueprints/START_HERE.md` with submodules `__init__.py`, `schema.py`, `builder.py`, `query.py`
- [x] 4.2 Add `linkgraph` row to the Package Map table in `blueprints/START_HERE.md`
- [x] 4.3 Add link graph navigation entries to the Navigation by Intent table in `blueprints/START_HERE.md`

## 5. Documentation Updates

- [x] 5.1 Update `plans/v2-master-plan.md` to mark sub-phases 10b through 10g as **Done**
- [x] 5.2 Review `lexibrary-overview.md` and update to reflect link graph behaviour: query-time dependents, `index.db` presence, graceful degradation
- [x] 5.3 Ensure `lexibrary-overview.md` describes `lexi lookup` as the source for reverse dependencies

## 6. TODO Cleanup and Test Verification

- [x] 6.1 Search for TODO comments in `src/lexibrarian/linkgraph/` and resolve or remove them
- [x] 6.2 Search for Phase 10-related TODOs in integration points (`archivist/pipeline.py`, `cli/`, `validator/`)
- [x] 6.3 Run the full test suite: `uv run pytest --cov=lexibrarian` and verify `linkgraph/` module coverage
- [x] 6.4 Run linter: `uv run ruff check src/ tests/` and fix any issues
- [x] 6.5 Run formatter: `uv run ruff format src/ tests/`
- [x] 6.6 Run type checker: `uv run mypy src/` and fix any issues
