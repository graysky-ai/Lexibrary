# linkgraph/query

**Summary:** Read-only query interface for the link graph SQLite index. Provides the `LinkGraph` class with methods for artifact lookups, reverse dependency queries, tag search, full-text search, convention inheritance, and multi-hop graph traversal. All methods return structured dataclasses rather than raw tuples. Supports graceful degradation via `LinkGraph.open()` returning `None`.

## Interface

| Name | Signature / Fields | Purpose |
| --- | --- | --- |
| `ArtifactResult` | dataclass: `id: int`, `path: str`, `kind: str`, `title: str \| None`, `status: str \| None` | Common return type for artifact lookups, tag search, and FTS search |
| `LinkResult` | dataclass: `source_id: int`, `source_path: str`, `link_type: str`, `link_context: str \| None` | Inbound link edge returned by `reverse_deps` |
| `TraversalNode` | dataclass: `artifact_id: int`, `path: str`, `kind: str`, `depth: int`, `via_link_type: str \| None` | Node discovered during multi-hop graph traversal |
| `ConventionResult` | dataclass: `body: str`, `directory_path: str`, `ordinal: int` | Local convention body scoped to a directory path |
| `BuildSummaryEntry` | dataclass: `action: str`, `count: int`, `total_duration_ms: int \| None` | Aggregate statistics for one action type in the most recent build |
| `LinkGraph` | class | Read-only query interface wrapping a SQLite connection |
| `open_index` | `(project_root: Path) -> LinkGraph \| None` | Module-level convenience: open `index.db` for queries, or `None` for graceful degradation |

## LinkGraph Class

### Construction

| Method | Signature | Purpose |
| --- | --- | --- |
| `__init__` | `(conn: sqlite3.Connection)` | Wrap an already-open connection; callers must ensure pragmas and schema version |
| `open` (classmethod) | `(db_path: str \| Path) -> LinkGraph \| None` | Open DB in **read-only** mode (SQLite URI `?mode=ro`), set pragmas, verify schema version; returns `None` on missing file, corruption, or version mismatch |

### Lifecycle

`LinkGraph` supports the context manager protocol:

- `close()` -- close the underlying SQLite connection
- `__enter__` / `__exit__` -- context manager that closes on exit

### Query Methods

| Method | Signature | Purpose |
| --- | --- | --- |
| `get_artifact` | `(path: str) -> ArtifactResult \| None` | Look up a single artifact by project-relative path |
| `resolve_alias` | `(alias: str) -> ArtifactResult \| None` | Resolve a concept alias (case-insensitive via COLLATE NOCASE) to its artifact |
| `reverse_deps` | `(path: str, link_type: str \| None = None) -> list[LinkResult]` | Return all inbound links to the artifact at path; optionally filter by link type |
| `search_by_tag` | `(tag: str) -> list[ArtifactResult]` | Find all artifacts tagged with the given tag (exact match) |
| `full_text_search` | `(query: str, limit: int = 20) -> list[ArtifactResult]` | FTS5 full-text search; query is literal-quoted to prevent FTS5 syntax errors; results ranked by relevance |
| `get_conventions` | `(directory_paths: list[str]) -> list[ConventionResult]` | Retrieve conventions for a list of directory paths, ordered root-to-leaf then by ordinal (convention inheritance) |
| `traverse` | `(start_path: str, max_depth: int = 3, link_types: list[str] \| None = None, direction: str = "outbound") -> list[TraversalNode]` | Multi-hop graph traversal via recursive CTE; supports outbound (forward deps) and inbound (reverse dep chain) directions |
| `build_summary` | `() -> list[BuildSummaryEntry]` | Aggregate statistics for the most recent build from build_log |

## Graceful Degradation

`LinkGraph.open()` returns `None` when:

- The database file does not exist on disk
- The database is corrupt (`sqlite3.DatabaseError`)
- The schema version is missing or does not match `SCHEMA_VERSION`

The module-level `open_index(project_root)` delegates to `LinkGraph.open()` and is the primary entry point for CLI consumers. Callers should branch on `None`:

```python
graph = open_index(project_root)
if graph is None:
    # Fall back to file-scanning search
    ...
```

## Multi-Hop Traversal Details

`traverse()` uses a recursive CTE with built-in cycle detection:

- A `visited` column accumulates a comma-separated list of artifact IDs along the current path
- The recursive step only follows an edge when the next node's ID does not appear in `visited`
- `max_depth` is clamped to a hard cap of `_MAX_DEPTH_CAP = 10` regardless of caller input
- `direction="outbound"` follows `source_id -> target_id` (forward dependencies)
- `direction="inbound"` follows `target_id -> source_id` (reverse dependency chain)
- `link_types` optionally restricts which edge types are followed
- The start node is excluded from results
- Results are ordered by depth then by path

## FTS5 Search Details

`full_text_search()` wraps the query string in double quotes to prevent FTS5 operator injection (`AND`, `OR`, `NOT`). Embedded double quotes are escaped by doubling (`"` -> `""`). Results are ordered by FTS5 relevance rank and capped by `limit`.

## Dependencies

- `lexibrary.linkgraph.schema` -- `SCHEMA_VERSION`, `check_schema_version`, `set_pragmas`
- `lexibrary.utils.paths` -- `LEXIBRARY_DIR` (imported inside `open_index()`)

## Dependents

- `lexibrary.linkgraph.__init__` -- eagerly re-exports `LinkGraph`, `open_index`, all result dataclasses
- `lexibrary.cli.lexi_app` -- `lookup` and `search` commands use `open_index()` to get a `LinkGraph`
- `lexibrary.search` -- `unified_search()` accepts `LinkGraph` for index-accelerated tag and FTS search
- `lexibrary.validator.checks` -- validation checks query the link graph for consistency checks

## Key Concepts

- `query.py` is the **read path** for the link graph; `builder.py` is the write path
- All queries use parameterised statements (`?` placeholders) for safety
- The read-only SQLite URI mode (`?mode=ro`) prevents accidental writes
- `open_index()` is the preferred consumer entry point; `LinkGraph.__init__` is for advanced use cases with pre-opened connections
- Convention inheritance is achieved by passing directory paths root-to-leaf to `get_conventions()`, which sorts results by caller-specified path order then ordinal
