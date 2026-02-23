# linkgraph/__init__

**Summary:** Package facade for the SQLite link graph index. Re-exports query-side and health-side symbols eagerly, and builder-side symbols lazily to avoid circular imports. The primary consumer-facing symbols are `open_index` (for `LinkGraph | None` query access) and `read_index_health` (for lightweight `IndexHealth` metadata without a full `LinkGraph`).

## Interface

| Name | Origin Module | Purpose |
| --- | --- | --- |
| `open_index` | `linkgraph.query` | Open the link graph index at `<project_root>/.lexibrary/index.db` for read-only queries; returns `LinkGraph \| None` for graceful degradation |
| `LinkGraph` | `linkgraph.query` | Read-only query class wrapping a SQLite connection; provides `reverse_deps`, `search_by_tag`, `full_text_search`, `get_conventions`, `traverse`, `build_summary` |
| `ArtifactResult` | `linkgraph.query` | Dataclass returned by artifact lookups, tag search, and FTS search |
| `LinkResult` | `linkgraph.query` | Dataclass for inbound link edges returned by `reverse_deps` |
| `TraversalNode` | `linkgraph.query` | Dataclass for multi-hop traversal results |
| `ConventionResult` | `linkgraph.query` | Dataclass for convention inheritance lookups |
| `BuildSummaryEntry` | `linkgraph.query` | Dataclass for build log aggregate statistics |
| `IndexHealth` | `linkgraph.health` | Dataclass with `artifact_count: int | None`, `link_count: int | None`, `built_at: str | None`; all fields `None` when index is absent/corrupt/version-mismatch |
| `read_index_health` | `linkgraph.health` | Lightweight helper: opens `index.db`, reads counts and `built_at` from `meta` table; returns `IndexHealth` with all-`None` fields for graceful degradation |
| `SCHEMA_VERSION` | `linkgraph.schema` | Current schema version string for compatibility checks |
| `check_schema_version` | `linkgraph.schema` | Verify the schema version in an open database |
| `ensure_schema` | `linkgraph.schema` | Create or migrate the schema in a writable database |
| `BuildResult` | `linkgraph.builder` | Lazy-loaded via `__getattr__`; result dataclass from `build_index` |
| `IndexBuilder` | `linkgraph.builder` | Lazy-loaded via `__getattr__`; incremental index builder class |
| `build_index` | `linkgraph.builder` | Lazy-loaded via `__getattr__`; top-level function to build/rebuild the index |

## Lazy Import Mechanism

Builder symbols (`BuildResult`, `IndexBuilder`, `build_index`) are listed in `__all__` and referenced in `TYPE_CHECKING` but are not imported at module load time. A module-level `__getattr__` function intercepts attribute access for these three names and imports `linkgraph.builder` on demand. This breaks a circular import cycle: `builder` depends on `archivist.dependency_extractor` which depends on `archivist.pipeline` which imports back into `linkgraph.builder`.

## Dependencies

- `lexibrary.linkgraph.health` -- eagerly imported for `IndexHealth`, `read_index_health`
- `lexibrary.linkgraph.query` -- eagerly imported for `open_index`, `LinkGraph`, result dataclasses
- `lexibrary.linkgraph.schema` -- eagerly imported for `SCHEMA_VERSION`, `check_schema_version`, `ensure_schema`
- `lexibrary.linkgraph.builder` -- lazily imported via `__getattr__` for `BuildResult`, `IndexBuilder`, `build_index`

## Dependents

- `lexibrary.cli.lexi_app` -- `lookup` and `search` commands import `open_index` from this package
- `lexibrary.cli.lexictl_app` -- `status` command imports `read_index_health` for link graph health display
- `lexibrary.search` -- `unified_search()` accepts `LinkGraph` (TYPE_CHECKING import from `linkgraph.query`)
- `lexibrary.archivist.pipeline` -- imports builder symbols for index rebuilds
- `lexibrary.validator.checks` -- link-graph checks import `SCHEMA_VERSION`, `check_schema_version`, `set_pragmas` from `linkgraph.schema`

## Key Concepts

- `open_index(project_root)` is the primary entry point for CLI consumers; it returns `LinkGraph | None` so callers can branch on `None` for graceful degradation (missing DB, corrupt DB, schema mismatch)
- All symbols are declared in `__all__` for explicit public API
- The package separates concerns into four submodules: `schema` (DDL), `builder` (write path), `query` (read path), `health` (lightweight metadata read)
- Storage location: `.lexibrary/index.db` (gitignored, rebuilt by `lexictl update`)
