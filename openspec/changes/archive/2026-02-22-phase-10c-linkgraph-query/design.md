## Context

Phase 10a delivered the SQLite schema for the link graph (`schema.py` with 8 tables + FTS5, `ensure_schema()`, `check_schema_version()`, pragma setup). Phase 10b (builder) is proceeding in parallel to populate the database. This design covers Phase 10c: the read-only query interface that all downstream consumers (CLI commands, validators, pipeline status) will use to access the link graph.

The existing schema module (`src/lexibrary/linkgraph/schema.py`) provides:
- `set_pragmas()` — WAL mode, foreign keys, synchronous=NORMAL
- `check_schema_version()` — returns `int | None`
- `ensure_schema()` — DDL creation/migration
- `SCHEMA_VERSION` constant (currently 2)

The query interface must be a pure consumer of the schema — it never modifies data. All write operations belong to the builder (10b).

## Goals / Non-Goals

**Goals:**
- Provide a single `LinkGraph` class as the read-only query interface for the link graph index
- Implement all key query patterns defined in the master plan (reverse deps, concept refs, tag search, FTS, alias resolution, convention inheritance, build summary)
- Implement `traverse()` for multi-hop graph traversal with cycle safety via recursive CTEs and `max_depth` guard (D-081)
- Graceful degradation when `index.db` is missing, corrupt, or version-mismatched (D-071)
- Expose `LinkGraph` in the `linkgraph/__init__.py` public API
- Return structured results (dataclasses/NamedTuples) not raw tuples

**Non-Goals:**
- No write operations — the query interface is strictly read-only
- No schema migration logic — that belongs to `schema.py` and the builder
- No CLI integration — that is Phase 10e
- No pipeline wiring — that is Phase 10d
- No validation checks — that is Phase 10f
- No caching layer — SQLite with WAL mode is fast enough for the expected query patterns

## Decisions

### D1: `LinkGraph` as context manager with `open()` factory

`LinkGraph.open(db_path)` is a `@classmethod` that returns `LinkGraph | None`. It returns `None` when:
1. The database file does not exist
2. `sqlite3.connect()` raises `sqlite3.DatabaseError` (corrupt file)
3. `check_schema_version()` returns `None` or a version mismatch

When it succeeds, it opens a connection with `set_pragmas()` applied and returns a `LinkGraph` instance wrapping the connection. The class implements `__enter__`/`__exit__` for use as a context manager (closes the connection on exit). It also supports explicit `close()`.

**Why a factory returning None instead of raising:** Callers (CLI commands, validators) should not need try/except blocks. The `None` sentinel makes graceful degradation a natural `if graph is None: skip` pattern. This matches D-071's specification.

**Alternative considered:** Raising a custom exception and catching at call sites. Rejected because every call site would need the same try/except boilerplate, and the behavior is always "skip gracefully."

### D2: Structured result types via `dataclasses`

Query methods return `dataclass` instances rather than raw tuples or dicts. Types defined at module level:

- `ArtifactResult(id, path, kind, title, status)` — common return type for artifact lookups
- `LinkResult(source_id, source_path, link_type, link_context)` — for reference/dependency queries
- `TraversalNode(artifact_id, path, kind, depth, via_link_type)` — for multi-hop results
- `ConventionResult(body, directory_path, ordinal)` — for convention inheritance
- `BuildSummaryEntry(action, count, total_duration_ms)` — for build summary

**Why dataclasses over NamedTuples:** Dataclasses support default values, optional fields, and are more idiomatic for Pydantic-heavy codebases. They also provide `__eq__` for testing.

### D3: Recursive CTE traversal with `max_depth` guard

`LinkGraph.traverse(start_path, max_depth=3, link_types=None, direction="outbound")` implements multi-hop graph traversal. The recursive CTE uses a `depth` counter that increments per hop and terminates at `max_depth`. A visited set in the CTE (`path NOT IN` or auxiliary visited table) prevents infinite loops on cyclic graphs.

The `direction` parameter supports:
- `"outbound"` — follow links from source to target (default, "what does this depend on?")
- `"inbound"` — follow links from target to source ("what depends on this?")

The `link_types` parameter optionally filters to specific link types (e.g., only `ast_import`).

**Why recursive CTE over application-level BFS:** SQLite recursive CTEs are executed server-side with no round-trip overhead per hop. For graphs with thousands of nodes, this is significantly faster than issuing one query per level. The `max_depth` guard (capped at a hard maximum of 10) ensures termination even if someone passes a large value.

**Alternative considered:** Application-level BFS with one query per depth level. Rejected for performance reasons and because cycle detection is cleaner in SQL (the CTE tracks visited nodes in the recursion).

### D4: Connection opened read-only with `uri=True` mode

The `LinkGraph` opens the SQLite connection using `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` to enforce read-only access at the SQLite level. This prevents accidental writes and provides a clear signal if any query accidentally includes a mutation.

**Why URI mode:** Standard `sqlite3.connect()` does not support read-only mode. The `uri=True` parameter with `?mode=ro` is the only way to get a read-only connection in Python's sqlite3 module.

### D5: All queries use parameterized statements

Every query method uses `?` parameter placeholders. No string interpolation or f-strings in SQL. This is defense-in-depth — while the query interface is internal (not user-facing SQL input), parameterized queries prevent bugs when paths contain special characters.

### D6: Module structure

All code lives in a single file `src/lexibrary/linkgraph/query.py`:
- Result dataclasses at the top
- `LinkGraph` class with `open()`, `close()`, `__enter__`/`__exit__`, and query methods
- Private helper methods prefixed with `_`

The file is expected to be ~300-400 lines. No submodules needed.

## Risks / Trade-offs

**[Risk] Recursive CTE performance on large cyclic graphs** --> Mitigated by `max_depth` hard cap of 10 and query-level `LIMIT`. Monitored via `build_log` timing when used in pipeline. If needed, a `LIMIT` clause can be added to the CTE result set.

**[Risk] WAL mode read-only connection compatibility** --> SQLite WAL mode allows concurrent readers alongside a single writer. Read-only connections via `?mode=ro` work correctly with WAL. However, WAL readers require the `-wal` and `-shm` files to exist. If these files are missing (e.g., database was copied without them), reads may fail. Mitigated by `open()` catching `DatabaseError`.

**[Risk] FTS5 MATCH syntax injection** --> FTS5 MATCH queries have their own syntax (AND, OR, NOT, column filters). User-provided search terms could accidentally trigger FTS syntax errors. Mitigated by wrapping search terms in double quotes in the `full_text_search()` method to treat them as literal phrases.

**[Trade-off] Returning `None` from `open()` vs raising exceptions** --> Choosing `None` optimizes for the common degradation path but means callers must check for `None`. Acceptable because callers are all internal code that we control, and the pattern is documented.

**[Trade-off] Single file vs multi-file module** --> A single `query.py` file keeps the module simple but could grow if many specialized query methods are added. Acceptable for the planned ~8 query methods; revisit if the file exceeds 500 lines.
