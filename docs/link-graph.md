# Link Graph

This guide explains the SQLite link graph index -- what it contains, how it is built, what queries it accelerates, and how to manage it.

## What Is the Link Graph?

The link graph is a SQLite database at `.lexibrary/index.db` that indexes all cross-references between Lexibrary artifacts. It enables fast queries for reverse dependencies, tag search, full-text search, convention inheritance, and multi-hop graph traversal.

The link graph is gitignored by default (it is a derived artifact that can be rebuilt from the source files at any time).

## Database Schema

The link graph uses 8 tables plus an FTS5 virtual table:

### 1. `meta`

Key-value store for schema version, build metadata, and aggregate counts.

| Key | Description |
|---|---|
| `schema_version` | Current schema version (used to detect when a rebuild is needed) |
| `built_at` | ISO 8601 timestamp of the most recent build |
| `builder` | Builder identifier (e.g., `lexibrary-v2`) |
| `artifact_count` | Total number of artifacts in the index |
| `link_count` | Total number of links in the index |

### 2. `artifacts`

Every indexed entity -- source files, design files, concepts, Stack posts, and conventions.

| Column | Description |
|---|---|
| `id` | Auto-incrementing primary key |
| `path` | Project-relative path (unique). Conventions use synthetic paths. |
| `kind` | One of: `source`, `design`, `concept`, `stack`, `convention` |
| `title` | Human-readable title (may be null) |
| `status` | Artifact status: `active`, `deprecated`, `draft`, `open`, `resolved`, `outdated`, `duplicate` (may be null) |
| `last_hash` | SHA-256 hash of the source file (for source artifacts) |
| `created_at` | Creation timestamp |

### 3. `links`

Directed edges between artifacts with typed relationships.

| Column | Description |
|---|---|
| `source_id` | FK to `artifacts.id` -- the artifact that holds the reference |
| `target_id` | FK to `artifacts.id` -- the artifact being referenced |
| `link_type` | The type of relationship (see Link Types below) |
| `link_context` | Optional contextual text for the link |

A unique constraint on `(source_id, target_id, link_type)` prevents duplicate links.

### 4. `tags`

Artifact-to-tag associations. Tags are shared across all artifact kinds in a single namespace.

### 5. `aliases`

Concept alias resolution. Each alias maps to exactly one concept artifact. Matching is case-insensitive (`COLLATE NOCASE`). Duplicates are resolved with first-writer-wins semantics.

### 6. `conventions`

Local conventions scoped to directories. Each convention has a `directory_path`, an `ordinal` (position within the directory), and a `body` (the convention text).

### 7. `build_log`

Per-artifact build tracking with timestamps, action types (`created`, `updated`, `deleted`, `unchanged`, `failed`), duration, and error messages. Entries older than 30 days are automatically cleaned up.

### 8. `artifacts_fts` (FTS5)

Full-text search virtual table using porter stemming and unicode61 tokenizer. Indexes artifact titles and bodies for fast text search.

## Link Types

The `links` table supports 8 link types:

| Link Type | Source | Target | Meaning |
|---|---|---|---|
| `ast_import` | source | source | Source file imports another source file (extracted via AST parsing) |
| `wikilink` | design or concept | concept | A `[[wikilink]]` reference to a concept |
| `stack_file_ref` | stack | source | Stack post references a source file (`refs.files`) |
| `stack_concept_ref` | stack | concept | Stack post references a concept (`refs.concepts`) |
| `design_stack_ref` | design | stack | Design file references a Stack post |
| `design_source` | design | source | Design file describes a source file |
| `concept_file_ref` | concept | source | Concept links to a source file |
| `convention_concept_ref` | convention | concept | Convention text references a concept via wikilink |

## How It Is Built

The link graph is built during `lexictl update` in one of two modes:

### Full Build

A full build runs when `lexictl update` is invoked without `--changed-only`. The pipeline:

1. Cleans stale build log entries (older than 30 days).
2. Ensures the schema exists (creates or recreates if the version mismatches).
3. Clears all existing data rows (preserves schema and meta).
4. Processes all artifact families in order:
   - **Design files** -- Creates source and design artifacts, `design_source` links, `ast_import` links (from AST parsing of the source file), `wikilink` links, `design_stack_ref` links, tags, and FTS rows.
   - **Concept files** -- Creates concept artifacts, aliases, `wikilink` links between concepts, `concept_file_ref` links, tags, and FTS rows.
   - **Stack posts** -- Creates stack artifacts, `stack_file_ref` links, `stack_concept_ref` links, tags, and FTS rows.
   - **`.aindex` conventions** -- Creates convention artifacts with synthetic paths, convention rows, `convention_concept_ref` links, and FTS rows.
5. Updates the meta table with build summary counts.
6. Commits the transaction.

The entire build (steps 3-5) runs in a single transaction. On unrecoverable failure, the transaction is rolled back leaving the database empty rather than partially populated. Per-artifact parse errors are caught and logged without aborting the build.

### Incremental Update

An incremental update runs when `lexictl update --changed-only <files>` is used. For each changed path:

1. The path is classified into an artifact kind (source, design, concept, stack, or aindex).
2. If the file no longer exists on disk, the corresponding artifact row is deleted. SQLite `ON DELETE CASCADE` automatically cleans up all related links, tags, aliases, conventions, and FTS rows.
3. If the file exists, outbound data (links, tags, aliases, FTS) is deleted and reinserted from the current file content.

## What Queries It Accelerates

### Reverse Dependencies in `lexi lookup`

When an agent runs `lexi lookup <file>`, the output includes a "Dependents" section showing files that import or reference the target file. This is powered by the `reverse_deps` query on the link graph, which finds all inbound `ast_import` links.

Without the link graph, dependents must be discovered by scanning all design files -- much slower for large projects.

### Tag Search in `lexi search`

`lexi search --tag <tag>` queries the `tags` table directly, returning all artifacts tagged with the given tag in constant time.

### Full-Text Search

`lexi search <query>` uses the `artifacts_fts` FTS5 table for fast full-text search across all indexed artifact titles and bodies. Results are ranked by FTS5 relevance.

### Convention Inheritance

`lexi lookup` retrieves applicable conventions for a file by querying the `conventions` table with the file's directory ancestry (root to leaf). Conventions are returned in inheritance order.

### Multi-Hop Traversal

The `LinkGraph.traverse()` method uses a recursive CTE to walk the link graph up to a configurable depth (default 3, max 10), with built-in cycle detection. This powers dependency chain analysis.

## Health Metadata in `lexictl status`

`lexictl status` reads link graph health from the `meta` table:

```
  Link graph: 156 artifacts, 342 links (built 2024-06-15T14:30:00+00:00)
```

When the index is absent:

```
  Link graph: not built (run lexictl update to create)
```

The health check reads only counts and the `built_at` timestamp -- it does not open the full query interface.

## Rebuilding the Index

To force a full rebuild of the link graph:

1. Delete the database file:
   ```bash
   rm .lexibrary/index.db
   ```
2. Run a full update:
   ```bash
   lexictl update
   ```

This is necessary when:

- The schema version changes (after a Lexibrary upgrade).
- The index becomes corrupt.
- You want to clean up stale artifacts from deleted files.

Note: `lexictl update` will always rebuild the index as part of its pipeline. You only need to delete `index.db` manually if you want to force a rebuild without re-running the full LLM pipeline (the index rebuild itself does not make LLM calls -- it reads existing artifacts from disk).

## Schema Version

The current schema version is stored in `meta.schema_version`. When Lexibrary opens the index, it checks this value against the expected version. If they do not match (e.g., after upgrading Lexibrary), the schema is automatically recreated on the next build.

## Graceful Degradation

All link graph queries are designed for graceful degradation. When the index is:

- **Missing** (`index.db` does not exist) -- Queries return empty results, and `lexi lookup` falls back to file scanning.
- **Corrupt** (cannot be opened or read) -- Returns `None` or empty results.
- **Schema mismatch** (version does not match) -- Returns empty results and logs a warning.

The link graph is always optional. Lexibrary works without it -- the index just makes certain queries faster.

## Validation Checks

Three validation checks query the link graph:

| Check | Severity | What It Does |
|---|---|---|
| `bidirectional_deps` | info | Compares design file dependency lists against `ast_import` links in the graph |
| `dangling_links` | info | Detects artifacts whose backing files no longer exist on disk |
| `orphan_artifacts` | info | Detects index entries for deleted files |

All three return empty results when the index is absent -- they never fail due to a missing index.

## Related Documentation

- [Design Files](design-files.md) -- The pipeline that builds the link graph
- [Configuration](configuration.md) -- No link graph-specific config (it is automatic)
- [Library Structure](library-structure.md) -- Where `index.db` lives in `.lexibrary/`
- [Validation](validation.md) -- Checks that query the link graph
- [Concepts](concepts.md) -- How concepts are indexed
- [Stack](stack.md) -- How Stack posts are indexed
- [Search](search.md) -- How the link graph accelerates search queries
- [Symbol Graph](symbol-graph.md) — symbol-level edges as a companion database.
