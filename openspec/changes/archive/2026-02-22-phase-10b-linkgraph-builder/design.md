## Context

Phase 10a delivered the SQLite schema (`src/lexibrarian/linkgraph/schema.py`) with 8 tables, an FTS5 virtual table, 13 indexes, and `ensure_schema()` / `check_schema_version()` utilities. The database file lives at `.lexibrary/index.db` and is gitignored -- it is always rebuildable from source artifacts.

The builder must populate this schema by reading four distinct artifact families:
1. **Design files** (`.lexibrary/src/**/*.md`) -- each corresponds to a source file; yields source artifacts, design artifacts, `design_source` links, `ast_import` links, `wikilink` links, `design_stack_ref` links, tags, and FTS content.
2. **Concept files** (`.lexibrary/concepts/*.md`) -- yield concept artifacts, aliases, concept-to-concept wikilinks, `concept_file_ref` links, tags, and FTS content.
3. **Stack posts** (`.lexibrary/stack/ST-*.md`) -- yield stack artifacts, `stack_file_ref` and `stack_concept_ref` links, tags, and FTS content.
4. **`.aindex` files** (`.lexibrary/src/**/.aindex`) -- yield convention artifacts from the `local_conventions` list, `convention_concept_ref` links, and FTS content.

Existing parsers handle all four families. The builder orchestrates them and writes to SQLite within a single transaction per build phase.

## Goals / Non-Goals

**Goals:**
- Implement `IndexBuilder` with `full_build()` and `incremental_update(changed_paths)` methods
- Populate all 8 tables plus FTS5 from existing parsed artifact models
- Handle edge cases: duplicate aliases, external imports, deleted files, FTS lifecycle
- Clean stale `build_log` entries (>30 days) at build start
- Provide accurate `meta` counts and `build_log` entries for observability
- Produce a `BuildResult` summary for callers

**Non-Goals:**
- Query interface (Phase 10c)
- Pipeline integration / calling the builder from `update_project` (Phase 10d)
- CLI integration / `lexi lookup` reverse links (Phase 10e)
- Multi-hop traversal or recursive CTEs (Phase 10c)
- Async or concurrent build (sequential is correct for MVP)

## Decisions

### D1: Single-class `IndexBuilder` with injected connection

The `IndexBuilder` class takes an open `sqlite3.Connection` (with pragmas already set) and the `project_root` as constructor arguments. It does not manage the database file lifecycle -- callers use `open_index()` to get a connection and `ensure_schema()` to prepare it. This keeps the builder testable with in-memory SQLite.

**Alternative considered:** Builder manages its own connection internally. Rejected because it prevents test isolation and makes transaction control opaque.

### D2: Full build uses a single transaction with explicit `BEGIN`/`COMMIT`

After clearing all rows, the builder inserts everything within one transaction. If any phase fails, the transaction is rolled back, leaving the database empty rather than partially populated. This is acceptable because the index is always rebuildable.

**Alternative considered:** Per-artifact-type transactions (one for design files, one for concepts, etc.). Rejected because partial indexes are worse than empty ones -- a half-built index gives wrong answers, while an empty one triggers graceful degradation.

### D3: Two-pass artifact insertion for link resolution

Artifacts are inserted in two passes:
1. **Pass 1 -- Insert all artifacts** (no links): design files, source files, concepts, Stack posts, conventions. This establishes `artifacts.id` values.
2. **Pass 2 -- Insert all links, tags, aliases, conventions, and FTS rows**: using the known artifact IDs from pass 1.

This avoids the problem of inserting a link from artifact A to artifact B when B hasn't been inserted yet. A single-pass approach would require deferred link insertion or `INSERT OR IGNORE` with retry, adding complexity.

**Alternative considered:** Single-pass with forward-reference buffering (collect links, insert after all artifacts). This is functionally equivalent but the two-pass structure is more readable and matches the schema's foreign key constraints.

### D4: Artifact path as the deduplication key

Every artifact is identified by its `path` column (UNIQUE constraint). Source files use their project-relative path. Design files use their `.lexibrary/` relative path. Concepts and Stack posts use their `.lexibrary/` relative paths. Conventions use the synthetic path `{directory_path}::convention::{ordinal}`.

The `::` separator in convention paths cannot appear in real filesystem paths on any supported OS, so collisions are impossible.

### D5: `_get_or_create_artifact()` helper for incremental updates

During incremental update, a changed design file may reference a concept that doesn't have an artifact row yet (e.g., a new `[[wikilink]]` added). The helper inserts a stub artifact if the target path doesn't exist in the artifacts table. For full builds, all artifacts are pre-inserted in pass 1, so this helper is a no-op.

### D6: FTS managed via explicit delete+reinsert

FTS5 standalone tables have no automatic sync. The builder:
- On full build: inserts FTS rows after artifact insertion (rowid = artifact.id)
- On incremental update: deletes the FTS row by rowid, then reinserts with updated content
- FTS body content varies by kind:
  - Source/design: `summary + "\n" + interface_contract`
  - Concept: `summary + "\n" + body`
  - Stack: `problem + "\n" + " ".join(answer.body for answer in answers)`
  - Convention: full body text

### D7: Alias collision handling -- first writer wins

When two concepts define the same alias (case-insensitive), the first concept processed gets the alias row. The second triggers a warning log: `"Alias '{alias}' already claimed by '{existing_concept}', skipping for '{current_concept}'"`. Processing order is deterministic (sorted by path) so the winner is stable across rebuilds.

### D8: Build log 30-day retention

At the start of every build (full or incremental), the builder deletes `build_log` rows where `build_started < now - 30 days`. This is a simple DELETE with a date comparison, executed before the main transaction.

### D9: External import filtering

`extract_dependencies()` already filters to project-internal paths (returns `None` for third-party imports). The builder simply skips `None` results. If a dependency resolves to a path that has no artifact row, the builder creates a stub `kind='source'` artifact for it (the source file exists but may not have a design file yet).

## Risks / Trade-offs

- **[Full rebuild is O(N) in total artifacts]** For a project with 500+ design files, 50 concepts, and 100 Stack posts, the full build reads ~650 markdown files and parses each one. This is I/O-bound, not LLM-bound. Mitigation: acceptable for MVP; incremental updates handle the common case. Profile after integration.

- **[Single transaction may hold a write lock for seconds]** WAL mode allows concurrent readers during the write, so `lexi lookup` queries are not blocked. The write lock duration is bounded by parse time (subsecond per file) plus insert time (microseconds per row). Mitigation: WAL mode + NORMAL synchronous already configured in schema pragmas.

- **[Incremental update may leave orphan artifacts]** If a design file is deleted but the builder only processes the source file change, the design artifact row remains. Mitigation: the builder checks for deleted files in `changed_paths` and removes their artifact rows (CASCADE handles links/tags). A periodic full rebuild (via `lexictl update`) is the safety net.

- **[FTS content can drift from source files]** If a design file's body changes but no incremental update is triggered, the FTS content is stale. Mitigation: `lexictl update` (full) rebuilds the entire FTS table. FTS staleness is a search quality issue, not a correctness issue.

- **[Convention synthetic paths are an internal convention]** The `{dir}::convention::{ordinal}` format is not validated at the schema level. Mitigation: the builder is the only writer; the pattern is documented and tested.

## Open Questions

None -- all design decisions are resolved by the master plan (D-068 through D-080) and the Phase 10a schema implementation.
