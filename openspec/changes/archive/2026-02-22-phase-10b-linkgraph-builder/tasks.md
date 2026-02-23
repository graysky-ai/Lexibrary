## 1. Data Models and Utilities

- [x] 1.1 Create `src/lexibrary/linkgraph/builder.py` with `from __future__ import annotations`, module docstring, and imports for sqlite3, logging, pathlib, datetime, and all artifact parsers
- [x] 1.2 Define `BuildResult` dataclass with fields: `artifact_count: int`, `link_count: int`, `duration_ms: int`, `errors: list[str]`, `build_type: str`
- [x] 1.3 Implement `_extract_wikilinks(text: str) -> list[str]` utility function using regex to find `[[...]]` patterns and return deduplicated names
- [x] 1.4 Write unit tests for `_extract_wikilinks` covering: multiple wikilinks, duplicates, no wikilinks, nested brackets edge case

## 2. IndexBuilder Class Foundation

- [x] 2.1 Implement `IndexBuilder.__init__(self, conn: sqlite3.Connection, project_root: Path)` that stores connection and project root, and calls `set_pragmas()` as a safety measure
- [x] 2.2 Implement `_clean_stale_build_log(self)` method that deletes `build_log` rows older than 30 days
- [x] 2.3 Implement `_clear_all_data(self)` method that deletes all rows from artifacts, links, tags, aliases, conventions, and artifacts_fts tables (preserving schema)
- [x] 2.4 Implement `_update_meta(self, build_started: str)` method that counts artifacts and links and updates meta table with `built_at`, `builder`, `artifact_count`, `link_count`
- [x] 2.5 Implement `_insert_artifact(self, path: str, kind: str, title: str | None, status: str | None, last_hash: str | None, created_at: str | None) -> int` that inserts an artifact row and returns the id
- [x] 2.6 Implement `_get_artifact_id(self, path: str) -> int | None` that looks up an artifact by path
- [x] 2.7 Implement `_get_or_create_artifact(self, path: str, kind: str, title: str | None = None) -> int` that returns existing id or inserts a stub
- [x] 2.8 Write unit tests for IndexBuilder foundation methods using in-memory SQLite

## 3. Full Build -- Design File Processing

- [x] 3.1 Implement `_scan_design_files(self) -> list[Path]` that discovers all `.md` files under `.lexibrary/src/` (the design file mirror tree)
- [x] 3.2 Implement `_process_design_file(self, design_path: Path, build_started: str)` that parses a design file and inserts: source artifact, design artifact, `design_source` link, `ast_import` links, `wikilink` links, `design_stack_ref` links, tags, and FTS row
- [x] 3.3 Handle source file hash computation: call `hash_file()` on the source file if it exists, use None if source file is missing
- [x] 3.4 Handle AST import extraction: call `extract_dependencies()` on the source file, filter to project-internal paths, create stub artifacts for import targets that lack artifacts, insert `ast_import` links
- [x] 3.5 Handle design file wikilinks: for each wikilink in `DesignFile.wikilinks`, resolve to concept path, `_get_or_create_artifact()` for the concept, insert `wikilink` link
- [x] 3.6 Handle design file Stack refs: for each ref in `DesignFile.stack_refs`, resolve to Stack post path, `_get_or_create_artifact()`, insert `design_stack_ref` link
- [x] 3.7 Write integration tests for design file processing with a sample design file in `tmp_path`

## 4. Full Build -- Concept File Processing

- [x] 4.1 Implement `_scan_concept_files(self) -> list[Path]` that discovers all `.md` files under `.lexibrary/concepts/`
- [x] 4.2 Implement `_process_concept_file(self, concept_path: Path, build_started: str)` that parses a concept file and inserts: concept artifact, aliases, `wikilink` links from body, `concept_file_ref` links, tags, and FTS row
- [x] 4.3 Handle alias uniqueness: attempt INSERT, catch UNIQUE constraint violation (or use INSERT OR IGNORE), log warning identifying both concepts for duplicate aliases
- [x] 4.4 Handle concept body wikilinks: call `_extract_wikilinks()` on concept body, `_get_or_create_artifact()` for each target concept, insert `wikilink` links
- [x] 4.5 Write integration tests for concept file processing including alias collision scenario

## 5. Full Build -- Stack Post Processing

- [x] 5.1 Implement `_scan_stack_posts(self) -> list[Path]` that discovers all `ST-*.md` files under `.lexibrary/stack/`
- [x] 5.2 Implement `_process_stack_post(self, stack_path: Path, build_started: str)` that parses a Stack post and inserts: stack artifact, `stack_file_ref` links, `stack_concept_ref` links, tags, and FTS row
- [x] 5.3 Handle Stack post FTS body: concatenate problem text and all answer bodies
- [x] 5.4 Write integration tests for Stack post processing

## 6. Full Build -- Convention Processing

- [x] 6.1 Implement `_scan_aindex_files(self) -> list[Path]` that discovers all `.aindex` files under `.lexibrary/`
- [x] 6.2 Implement `_process_aindex_conventions(self, aindex_path: Path, build_started: str)` that parses an `.aindex` file and for each local convention: inserts a convention artifact with synthetic path, inserts a conventions table row, extracts wikilinks, inserts `convention_concept_ref` links, inserts FTS row
- [x] 6.3 Generate synthetic paths using `{directory_path}::convention::{ordinal}` format
- [x] 6.4 Write integration tests for convention processing including wikilink extraction from convention text

## 7. Full Build Orchestration

- [x] 7.1 Implement `full_build(self) -> BuildResult` that orchestrates the complete pipeline: clean stale build log, ensure schema, clear all data, process all artifact types in two passes (pass 1: insert artifacts; pass 2: insert links/tags/aliases/FTS), update meta, return BuildResult
- [x] 7.2 Wrap the main build in a transaction with rollback on failure
- [x] 7.3 Implement timing: capture start time, compute `duration_ms` for BuildResult
- [x] 7.4 Implement error collection: catch per-artifact errors, log them, add to BuildResult.errors, continue processing
- [x] 7.5 Write end-to-end integration test for `full_build()` with a sample project tree containing design files, concepts, Stack posts, and .aindex files

## 8. Incremental Update

- [x] 8.1 Implement `_classify_path(self, file_path: Path) -> str` that returns artifact kind based on file path (concept, stack, aindex, design, source)
- [x] 8.2 Implement `_delete_artifact_outbound(self, artifact_id: int)` that deletes all outbound links, tags, aliases, and FTS row for an artifact
- [x] 8.3 Implement `_handle_deleted_file(self, file_path: Path, build_started: str)` that deletes the artifact row (CASCADE handles cleanup) and logs to build_log
- [x] 8.4 Implement `_handle_changed_source(self, file_path: Path, build_started: str)` that re-reads the source file and its design file, deletes outbound data, and reinserts links/tags/FTS
- [x] 8.5 Implement `_handle_changed_concept(self, file_path: Path, build_started: str)` that re-parses the concept file, deletes outbound data, and reinserts aliases/links/tags/FTS
- [x] 8.6 Implement `_handle_changed_stack(self, file_path: Path, build_started: str)` that re-parses the Stack post, deletes outbound data, and reinserts links/tags/FTS
- [x] 8.7 Implement `_handle_changed_design(self, file_path: Path, build_started: str)` that re-parses the design file, deletes outbound data, reinserts links/tags/FTS, and re-extracts AST imports for the associated source file
- [x] 8.8 Implement `_handle_changed_aindex(self, file_path: Path, build_started: str)` that deletes all convention artifacts for the directory, re-parses, and reinserts
- [x] 8.9 Implement `incremental_update(self, changed_paths: list[Path]) -> BuildResult` that classifies each path, dispatches to the appropriate handler, updates meta, and returns BuildResult
- [x] 8.10 Write integration tests for incremental update: modified source file, deleted file, modified concept with alias change, modified .aindex conventions

## 9. Public API and Module Exports

- [x] 9.1 Implement `build_index(project_root: Path, changed_paths: list[Path] | None = None) -> BuildResult` module-level function that opens/creates the database, constructs IndexBuilder, and delegates to full_build or incremental_update
- [x] 9.2 Implement `open_index(project_root: Path) -> sqlite3.Connection | None` that opens `.lexibrary/index.db` with pragmas, returns None if missing or corrupt
- [x] 9.3 Update `src/lexibrary/linkgraph/__init__.py` to export `IndexBuilder`, `BuildResult`, `build_index`, and `open_index`
- [x] 9.4 Write integration tests for `build_index()` and `open_index()` public API functions

## 10. Final Validation

- [x] 10.1 Run full test suite: `uv run pytest --cov=lexibrary tests/`
- [x] 10.2 Run linter: `uv run ruff check src/ tests/`
- [x] 10.3 Run formatter: `uv run ruff format src/ tests/`
- [x] 10.4 Run type checker: `uv run mypy src/`
- [x] 10.5 Verify all new modules have `from __future__ import annotations`
- [x] 10.6 Verify no bare `print()` calls (all output via `logging` or `rich.console.Console`)
