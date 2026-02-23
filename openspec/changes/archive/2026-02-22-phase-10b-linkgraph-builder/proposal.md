## Why

The Phase 10a schema defines 8 SQLite tables plus an FTS5 virtual table for the link graph index, but nothing populates them yet. Without a builder, the `index.db` file remains empty and all downstream features -- reverse dependency lookups, accelerated tag search, full-text search, alias resolution, and convention inheritance queries -- are inoperable. The builder is the prerequisite for the query interface (10c), pipeline integration (10d), and CLI enhancements (10e).

## What Changes

- Implement `IndexBuilder` class in `src/lexibrary/linkgraph/builder.py` with two primary methods:
  - `full_build()` — scans all design files, concept files, Stack posts, and `.aindex` local conventions; populates all 8 tables plus FTS5; updates `meta` and logs to `build_log`
  - `incremental_update(changed_paths)` — deletes outbound links/tags/aliases/FTS for changed files, re-extracts and re-inserts from current content, handles deleted files via CASCADE
- Update `src/lexibrary/linkgraph/__init__.py` to expose `IndexBuilder` and the `build_index()` / `open_index()` public API functions
- Add build log housekeeping: entries older than 30 days are cleaned at the start of each build
- Filter external package imports to project-internal paths only (no artifact rows for third-party modules)
- Handle `aliases.alias` UNIQUE constraint conflicts (first concept wins, log warning)
- Manage FTS5 as a standalone table with explicit delete+reinsert (no trigger sync)

## Capabilities

### New Capabilities
- `linkgraph-full-build`: Full index build that scans all artifact types (design files, concepts, Stack posts, conventions) and populates all SQLite tables including FTS5
- `linkgraph-incremental-update`: Incremental index update for a set of changed file paths, with delete-and-reinsert semantics and CASCADE handling for deletions

### Modified Capabilities

## Impact

- **New file:** `src/lexibrary/linkgraph/builder.py` (new module)
- **Modified file:** `src/lexibrary/linkgraph/__init__.py` (new exports)
- **Dependencies consumed:** `artifacts.design_file` (DesignFile model), `artifacts.design_file_parser` (parse_design_file), `artifacts.concept` (ConceptFile model), `wiki.parser` (parse_concept_file), `wiki.index` (ConceptIndex), `stack.models` (StackPost model), `stack.parser` (parse_stack_post), `artifacts.aindex` (AIndexFile model), `artifacts.aindex_parser` (parse_aindex), `archivist.dependency_extractor` (extract_dependencies), `linkgraph.schema` (ensure_schema, SCHEMA_VERSION, set_pragmas), `utils.hashing` (hash_file)
- **No new external dependencies** -- `sqlite3` is in the Python standard library
- **Phase:** 10b (depends on 10a which is complete; can run in parallel with 10c)
- **Reference decisions:** D-068, D-069, D-074, D-075, D-076, D-077, D-078, D-079, D-080
