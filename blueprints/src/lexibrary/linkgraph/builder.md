# linkgraph/builder

**Summary:** Populates the SQLite link graph index from parsed artifact families (design files, concept files, Stack posts, convention files). Provides `IndexBuilder` class with `full_build()` and `incremental_update()` entry points, plus the module-level `build_index()` convenience function.

## Interface

| Name | Signature / Fields | Purpose |
| --- | --- | --- |
| `BuildResult` | dataclass: `artifact_count: int`, `link_count: int`, `duration_ms: int`, `errors: list[str]`, `build_type: str` | Summary returned by `full_build()` and `incremental_update()` |
| `IndexBuilder` | `(conn: sqlite3.Connection, project_root: Path)` | Main builder class; wraps a SQLite connection and project root |
| `IndexBuilder.full_build` | `() -> BuildResult` | Clear all data and rebuild from scratch |
| `IndexBuilder.incremental_update` | `(changed_paths: list[Path]) -> BuildResult` | Reprocess only changed/deleted files |
| `build_index` | `(project_root: Path, changed_paths: list[Path] \| None = None) -> BuildResult` | Module-level convenience: opens/creates `index.db`, runs full or incremental build, closes connection |
| `open_index` | `(project_root: Path) -> sqlite3.Connection \| None` | Open existing `index.db` with pragmas; returns `None` if missing/corrupt |

## Full Build Pipeline

`full_build()` executes the following steps, wrapped in a single transaction (steps 3-5):

1. **Ensure schema** -- `ensure_schema(conn)` creates or recreates tables if version mismatches
2. **Clean stale build log** -- delete `build_log` entries older than 30 days
3. **Clear all data** -- delete rows from artifacts, links, tags, aliases, conventions, artifacts_fts (preserves meta and build_log)
4. **Process all artifact families** in order:
   - 4a. **Design files** -- scan `.lexibrary/src/**/*.md`; for each: parse design file, insert source artifact (with hash), insert design artifact, insert `design_source` link, extract `ast_import` links via tree-sitter, insert `wikilink` links to concepts, insert `design_stack_ref` links, insert tags, insert FTS row
   - 4b. **Concept files** -- scan `.lexibrary/concepts/**/*.md`; for each: parse concept file, insert/update concept artifact (reuses stubs), insert aliases (first-writer-wins), insert `wikilink` links, insert `concept_file_ref` links, insert tags, insert FTS row
   - 4c. **Stack posts** -- scan `.lexibrary/stack/ST-*.md`; for each: parse Stack post, insert/update stack artifact, insert `stack_file_ref` links, insert `stack_concept_ref` links, insert tags, insert FTS row
   - 4d. **Convention files** -- scan `.lexibrary/conventions/*.md`; for each: parse convention file via `parse_convention_file()`, insert convention artifact (path = convention file relpath), insert `conventions` table row (with `directory_path` from scope, `source`, `status`, `priority`), extract `convention_concept_ref` wikilinks from body, insert tags, insert FTS row (body = rule + body)
5. **Update meta** -- write `built_at`, `builder`, `artifact_count`, `link_count` to `meta` table
6. **Commit** -- on success; rollback on unrecoverable failure (leaves DB empty rather than partially populated)

Per-artifact parse errors are caught and collected in `BuildResult.errors` without aborting the build.

## Incremental Update Pipeline

`incremental_update(changed_paths)` processes only specified files:

1. **Ensure schema** and **clean stale build log**
2. For each path in `changed_paths`:
   - **Classify** the path into artifact kind (concept/stack/convention/aindex/design/source) via `_classify_path()`
   - If file **deleted**: remove artifact row (CASCADE handles cleanup for links, tags, aliases); explicitly delete FTS row (standalone FTS5 tables are not covered by CASCADE)
   - If file **modified**: dispatch to kind-specific handler:
     - `_handle_changed_source` -- re-hash, delete outbound data, re-extract AST imports, re-process associated design file if exists
     - `_handle_changed_concept` -- re-parse, delete outbound data, re-insert aliases/links/tags/FTS
     - `_handle_changed_stack` -- re-parse, delete outbound data, re-insert links/tags/FTS
     - `_handle_changed_convention` -- re-parse, delete convention table row and outbound data, re-insert convention artifact/row/links/tags/FTS with extended metadata (source, status, priority)
     - `_handle_changed_design` -- re-parse, delete outbound data, re-insert links/tags/FTS, re-extract AST imports for associated source
3. **Update meta** and **commit**

## Convention Processing

Convention files are read from `.lexibrary/conventions/*.md` and parsed via `parse_convention_file()` from `lexibrary.conventions.parser`. For each convention file:

1. Parse the file to get `ConventionFile` with frontmatter (title, scope, status, source, priority, tags) and body
2. Derive `directory_path` from scope: `"project"` maps to `"."`, otherwise use scope value directly
3. Compute ordinal as next available within the directory_path
4. Insert convention artifact with path = convention file relpath
5. Insert `conventions` table row with extended metadata (`source`, `status`, `priority`)
6. Extract `[[wikilinks]]` from body and insert `convention_concept_ref` links
7. Insert FTS row (body = rule + body text)
8. Insert tags from frontmatter

## Forward Reference Handling

The builder uses `_get_or_create_artifact()` to handle forward references. When a link target (e.g., a concept referenced by a wikilink) does not yet have an artifact row, a stub is created with minimal fields. When the actual file is processed later, the stub is updated with full details (title, status, hash). This is functionally equivalent to a two-pass design (D3) but implemented in a single pass.

## Internal Helpers

| Name | Purpose |
| --- | --- |
| `_extract_wikilinks` | Regex extraction of `[[wikilink]]` targets from text; deduplicates preserving first-occurrence order |
| `_clean_stale_build_log` | Delete build_log rows older than 30 days |
| `_clear_all_data` | Delete from artifacts, links, tags, aliases, conventions, artifacts_fts (preserves meta, build_log) |
| `_update_meta` | Write build summary counts and timestamp to meta table |
| `_insert_artifact` | Insert a row into artifacts, return new row id |
| `_get_artifact_id` | Look up artifact by path, return id or None |
| `_get_or_create_artifact` | Return existing id or insert stub; handles forward references |
| `_insert_link` | INSERT OR IGNORE into links (dedup on unique constraint) |
| `_insert_tag` | INSERT OR IGNORE into tags |
| `_insert_fts` | Insert FTS5 row (rowid must match artifacts.id) |
| `_insert_alias` | INSERT OR IGNORE with first-writer-wins; logs warning on collision |
| `_classify_path` | Determine artifact kind from file path prefix and extension (concept/stack/convention/aindex/design/source) |
| `_delete_artifact_outbound` | Delete outbound links, tags, aliases, FTS for an artifact (preserves artifact row) |
| `_design_path_to_source_relpath` | Convert `.lexibrary/src/foo.py.md` to `src/foo.py` |
| `_compute_source_hash` | SHA-256 hash of source file, or None if missing |
| `_extract_ast_imports` | Extract AST imports via tree-sitter and insert `ast_import` links (lazy import to break circular dependency) |
| `_process_design_wikilinks` | Insert `wikilink` links from design file to concepts |
| `_process_design_stack_refs` | Insert `design_stack_ref` links from design file to Stack posts |
| `_scan_convention_files` | Discover all `.md` files under `.lexibrary/conventions/`; sorted for deterministic order |
| `_process_convention_file` | Parse a convention file and insert artifact, conventions row, links, tags, FTS |
| `_handle_changed_convention` | Incremental handler for modified convention files |

## Dependencies

- `lexibrary.linkgraph.schema` -- `ensure_schema`, `set_pragmas`
- `lexibrary.archivist.dependency_extractor` -- `extract_dependencies` for AST import extraction (lazy import to break circular dependency)
- `lexibrary.artifacts.design_file_parser` -- `parse_design_file`
- `lexibrary.conventions.parser` -- `parse_convention_file`
- `lexibrary.wiki.parser` -- `parse_concept_file`
- `lexibrary.stack.parser` -- `parse_stack_post`
- `lexibrary.utils.hashing` -- `hash_file`
- `lexibrary.utils.paths` -- `LEXIBRARY_DIR`

## Dependents

- `lexibrary.linkgraph.__init__` -- lazy-imports `BuildResult`, `IndexBuilder`, `build_index` via `__getattr__`
- `lexibrary.archivist.pipeline` -- calls `build_index()` after design file generation
- `lexibrary.cli.lexictl_app` -- `update` command invokes `build_index()` for full or incremental builds

## Key Concepts

- The builder is the **write path** for the link graph; `query.py` is the read path
- `build_index()` is the preferred entry point for callers who do not need to manage the database connection
- The full build is wrapped in a single transaction for atomicity; on failure, the transaction is rolled back leaving the DB empty rather than partially populated
- `_BUILDER_ID = "lexibrary-v2"` is stored in the `meta` table for provenance
- `_STALE_LOG_DAYS = 30` controls build log retention
- FTS5 is managed manually (standalone table with no content sync); the builder handles all inserts/deletes/updates directly
- Alias uniqueness uses first-writer-wins semantics with COLLATE NOCASE; sorted file processing ensures deterministic winners
- Convention files use the real file path (e.g., `.lexibrary/conventions/use-type-hints.md`) as the artifact path, not synthetic paths
- The `extract_dependencies` import is deferred (lazy) to break the circular import: builder -> archivist.dependency_extractor -> archivist -> pipeline -> builder
