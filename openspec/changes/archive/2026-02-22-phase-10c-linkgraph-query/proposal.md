## Why

The link graph schema (Phase 10a) and builder (Phase 10b, in parallel) establish the SQLite index, but no code can read from it yet. Without a query interface, CLI commands like `lexi lookup`, `lexi search --tag`, and `lexictl status` cannot leverage reverse dependency lookups, full-text search, or tag acceleration. Phase 10c delivers the read-only `LinkGraph` query class so that downstream phases (10d pipeline integration, 10e CLI integration, 10f validation) have a stable API to consume.

## What Changes

- New `LinkGraph` class in `src/lexibrary/linkgraph/query.py` providing read-only query methods against `index.db`
- `LinkGraph.open()` factory with graceful degradation: returns `None` when `index.db` is missing, corrupt, or has a schema version mismatch (D-071)
- Query methods for all key access patterns: reverse deps, concept references, tag search, full-text search, alias resolution, convention inheritance, and build summary
- `LinkGraph.traverse()` for multi-hop graph traversal using recursive CTEs with configurable `max_depth` (default: 3) to prevent runaway queries on cyclic graphs (D-081)
- Updated `linkgraph/__init__.py` to expose `LinkGraph` in the public API
- WAL mode enabled on every connection open for concurrent read/write safety

## Capabilities

### New Capabilities
- `linkgraph-query`: Read-only `LinkGraph` query interface with graceful degradation, multi-hop traversal, and all key query patterns (reverse deps, tag search, full-text search, alias resolution, convention inheritance, build summary)

### Modified Capabilities
<!-- No existing spec-level requirements are changing. The schema (10a) is consumed as-is. -->

## Impact

- **Code:** New file `src/lexibrary/linkgraph/query.py`, updated `src/lexibrary/linkgraph/__init__.py`
- **APIs:** New `LinkGraph` class becomes the public read interface for all link graph consumers (CLI commands, validators, pipeline)
- **Dependencies:** None (uses stdlib `sqlite3`)
- **Downstream unblocked:** Phases 10d (pipeline integration), 10e (CLI integration), and 10f (validation/status) all depend on this query interface
