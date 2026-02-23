# linkgraph/schema

**Summary:** DDL constants and schema management for the link graph SQLite index. Defines the 8-table + FTS5 structure, connection pragmas, schema versioning, and the `ensure_schema()` entry point that creates or recreates the database schema.

## Interface

| Name | Signature / Type | Purpose |
| --- | --- | --- |
| `SCHEMA_VERSION` | `int` (currently `2`) | Schema version stored in `meta` table; mismatch on open triggers a full rebuild |
| `set_pragmas` | `(conn: sqlite3.Connection) -> None` | Set WAL mode, foreign keys ON, and synchronous NORMAL on a connection |
| `check_schema_version` | `(conn: sqlite3.Connection) -> int \| None` | Read the stored schema version from `meta`; returns `None` if table missing, row missing, or value not a valid integer |
| `ensure_schema` | `(conn: sqlite3.Connection, *, force: bool = False) -> bool` | Create or recreate the schema; returns `True` if schema was (re)created, `False` if already up to date |

## Database Schema

The link graph uses 8 tables plus an FTS5 virtual table:

| # | Table | Purpose |
| --- | --- | --- |
| 1 | `meta` | Key-value store for schema version, build metadata (`built_at`, `builder`, `artifact_count`, `link_count`) |
| 2 | `artifacts` | Every indexed entity: `id` (PK), `path` (UNIQUE), `kind` (CHECK: source/design/concept/stack/convention), `title`, `status`, `last_hash`, `created_at` |
| 3 | `links` | Directed edges between artifacts: `source_id` -> `target_id` with `link_type` (CHECK: ast_import/wikilink/stack_file_ref/stack_concept_ref/design_stack_ref/design_source/concept_file_ref/convention_concept_ref) and optional `link_context`; UNIQUE on (source_id, target_id, link_type) |
| 4 | `tags` | Artifact-to-tag associations (shared namespace per D-037); UNIQUE on (artifact_id, tag) |
| 5 | `aliases` | Concept alias resolution; `alias` column uses COLLATE NOCASE; UNIQUE on (alias) for first-writer-wins semantics |
| 6 | `conventions` | Local conventions scoped to directories: `directory_path`, `ordinal`, `body`; UNIQUE on (directory_path, ordinal) |
| 7 | `build_log` | Per-artifact build tracking: `build_started`, `build_type` (full/incremental), `artifact_path`, `artifact_kind`, `action` (created/updated/deleted/unchanged/failed), `duration_ms`, `error_message` |
| 8 | `artifacts_fts` | FTS5 virtual table (standalone, no content table): `title` + `body` columns; porter stemming + unicode61 tokenizer |

## Indexes

The schema creates 12 secondary indexes for query performance:

- `artifacts`: path, kind, status (partial: WHERE status IS NOT NULL)
- `links`: source_id, target_id, link_type, (target_id, link_type) composite
- `tags`: tag, artifact_id
- `aliases`: artifact_id
- `conventions`: directory_path
- `build_log`: build_started, artifact_path

## Pragmas

Set on every connection open via `set_pragmas()`:

- `journal_mode = WAL` -- write-ahead logging for concurrent reads
- `foreign_keys = ON` -- enforce FK constraints and CASCADE deletes
- `synchronous = NORMAL` -- balanced durability/performance

## Schema Lifecycle

`ensure_schema(conn, force=False)` follows this logic:

1. Call `set_pragmas(conn)` to configure the connection
2. Read `check_schema_version(conn)` to get the stored version
3. If `force=False` and version matches `SCHEMA_VERSION`, return `False` (no-op)
4. Otherwise, drop all tables in FK-safe order (`_drop_all`) and recreate from DDL (`_create_all`)
5. Seed `meta` with `schema_version` and `built_at` timestamp
6. Commit and return `True`

The drop order respects foreign key dependencies: build_log, conventions, aliases, tags, links, artifacts_fts, artifacts, meta.

## Dependencies

- `sqlite3` (stdlib)
- `datetime` (stdlib) -- UTC timestamps for `built_at`

## Dependents

- `lexibrarian.linkgraph.__init__` -- re-exports `SCHEMA_VERSION`, `check_schema_version`, `ensure_schema`
- `lexibrarian.linkgraph.builder` -- calls `ensure_schema()` and `set_pragmas()` during builds
- `lexibrarian.linkgraph.query` -- imports `SCHEMA_VERSION`, `check_schema_version`, `set_pragmas` for `LinkGraph.open()` validation
- `lexibrarian.linkgraph.health` -- imports `SCHEMA_VERSION`, `check_schema_version`, `set_pragmas` for `read_index_health()`
- `lexibrarian.validator.checks` -- link-graph validation checks import `SCHEMA_VERSION`, `check_schema_version`, `set_pragmas`
