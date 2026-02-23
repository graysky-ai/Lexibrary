## Why

The link graph index (Phase 10a schema, 10b builder, 10c query interface) provides accelerated cross-artifact queries, but none of this power is surfaced through CLI commands yet. Agents using `lexi lookup` get no reverse dependency information, `lexi search --tag` performs O(N) file scanning, and there is no full-text search at all. This change wires the read-only `LinkGraph` query interface into the CLI so agents get richer context with better performance -- completing the Phase 10 critical path (10a -> 10b -> 10d -> 10e).

## What Changes

- `lexi lookup <file>` gains a `## Dependents` and `## Also Referenced By` section after the existing conventions output, showing reverse links from the link graph index. If `index.db` is unavailable, this section is silently omitted (graceful degradation).
- `lexi search --tag <t>` gains an index-accelerated code path that queries the `tags` table for O(1) lookup. Falls back to the existing file-scanning implementation when the index is unavailable.
- `lexi search <query>` (free-text without `--tag`) gains FTS5-powered full-text search that returns ranked, grouped results across all artifact types. Full-text search requires the index -- no fallback (returns an informative message if index is missing).
- `unified_search()` in `search.py` gains an optional `link_graph` parameter to use the index-accelerated paths when available.

## Capabilities

### New Capabilities
- `lookup-reverse-links`: Display reverse dependency and cross-reference information in `lexi lookup` output using the link graph index, with graceful degradation when the index is unavailable.
- `fts-search`: FTS5-powered full-text search across all artifact types via `lexi search <query>`, returning ranked results grouped by type (concepts, design files, Stack posts). Requires the link graph index.
- `accelerated-tag-search`: Index-accelerated tag queries via `lexi search --tag <t>` using the `tags` table, with automatic fallback to file-scanning when the index is unavailable.

### Modified Capabilities
- `unified-search`: The `unified_search()` function gains an index-accelerated code path for tag queries and a new FTS code path for free-text queries, alongside the existing file-scanning paths.
- `lookup-conventions`: The `lexi lookup` command gains additional output sections after the existing conventions display.

## Impact

- **Modified files:**
  - `src/lexibrary/cli/lexi_app.py` -- `lookup` command gains reverse-link display; `search` command gains FTS/tag acceleration dispatch
  - `src/lexibrary/search.py` -- `unified_search()` gains `link_graph` parameter and index-accelerated code paths
  - `src/lexibrary/linkgraph/__init__.py` -- re-exports `open_index` from query module
- **Depends on (must exist before implementation):**
  - `src/lexibrary/linkgraph/query.py` (Phase 10c) -- `LinkGraph` class with `reverse_deps()`, `references_to()`, `search_tag()`, `search_fts()` methods
  - `src/lexibrary/linkgraph/schema.py` (Phase 10a) -- already complete
- **No new dependencies** -- `sqlite3` is in Python's standard library
- **Reference decisions:** D-070 (graceful degradation), D-071 (reverse links in lookup), D-075 (FTS5 search)
