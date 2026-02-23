## Context

Lexibrary's Phase 10 builds a SQLite-backed link graph index (`index.db`) that tracks all cross-artifact relationships. The schema (10a) and query interface (10c) are prerequisites for this change. The builder (10b) and pipeline integration (10d) populate the index during `lexictl update`.

Currently, agents using `lexi lookup` see the design file and inherited conventions but have no visibility into what depends on a file. The `lexi search` command performs O(N) file scanning for both tag and free-text queries. Phase 10e closes the loop by surfacing link graph data through existing CLI commands.

The key constraint is **graceful degradation**: agents must never be blocked by a missing or corrupt `index.db`. The index is a performance accelerator and data enrichment layer, not a hard dependency.

## Goals / Non-Goals

**Goals:**
- Surface reverse dependency and cross-reference data in `lexi lookup` output
- Accelerate `lexi search --tag` with O(1) index lookups, falling back to file scanning
- Enable ranked full-text search via FTS5 through `lexi search <query>`
- Maintain zero-breakage when `index.db` is missing, corrupt, or stale

**Non-Goals:**
- Building or rebuilding the index (that is Phase 10b/10d -- `lexictl update`)
- Adding new CLI commands (we are enriching existing `lookup` and `search`)
- Modifying `lexictl status` or `lexictl validate` (that is Phase 10f)
- Implementing the `LinkGraph` query class itself (that is Phase 10c)
- Any changes to `lexictl` commands -- this change is purely `lexi` (agent-facing)

## Decisions

### D1: `open_index()` returns `LinkGraph | None` -- callers branch on None

The `open_index(project_root)` function from Phase 10c attempts to open `index.db`, verify the schema version, and return a `LinkGraph` instance. If anything fails (missing file, corrupt DB, version mismatch), it returns `None`. CLI commands check for `None` and skip index-dependent features.

**Alternative considered:** Raising exceptions and catching at the CLI layer. Rejected because every call site would need identical try/except boilerplate, and the "missing index" case is normal operation (not exceptional).

### D2: Reverse links in `lookup` are displayed after conventions, in two groups

The output appends two sections after `## Applicable Conventions`:
1. `## Dependents (imports this file)` -- `ast_import` links where this file is the target
2. `## Also Referenced By` -- all other inbound link types (wikilinks from concepts, Stack post file refs, design file Stack refs)

This matches the master plan's specified output format. Import dependencies are separated because they are the most actionable for agents (understanding call chains). The "Also Referenced By" section provides broader context without cluttering the primary dependency view.

**Alternative considered:** A single flat "Referenced By" list. Rejected because agents need to distinguish "what code depends on this" from "what documentation references this."

### D3: Tag search uses dual code path with transparent fallback

`unified_search()` accepts an optional `link_graph: LinkGraph | None` parameter. When a `LinkGraph` is available and the caller passes `tag` (without free-text `query`), the function queries the `tags` table directly. When the index is unavailable, it falls back to the existing file-scanning code paths.

The caller (`search` command in `lexi_app.py`) is responsible for calling `open_index()` and passing the result. This keeps `search.py` decoupled from SQLite.

**Alternative considered:** Having `unified_search()` call `open_index()` internally. Rejected because it couples the search module to the linkgraph module and makes testing harder.

### D4: FTS search is index-only -- no file-scanning fallback

Full-text search via `lexi search <query>` (without `--tag`) uses FTS5 when the index is available. When the index is unavailable, the existing file-scanning free-text search remains as the fallback. This existing fallback matches against description + source_path + tags (a substring match, not ranked).

The FTS path returns ranked results via FTS5's `rank` column, which provides substantially better relevance than substring matching. The CLI dispatches to FTS when the index is available and falls back to the existing path when it is not.

### D5: `LinkGraph` query methods map directly to SQL queries from the master plan

The `LinkGraph` class (Phase 10c) exposes methods that map to the "Key Queries" section of the master plan:
- `reverse_deps(path) -> list[str]` -- inbound `ast_import` links
- `references_to(path) -> list[tuple[str, str, str]]` -- all inbound links with `(source_path, link_type, kind)`
- `search_tag(tag) -> list[tuple[str, str, str]]` -- `(path, kind, title)` from `tags` table join
- `search_fts(query) -> list[tuple[str, str, str]]` -- `(path, kind, title)` from FTS5 match

These return plain tuples/lists, not Pydantic models, to keep the query layer lightweight and avoid importing artifact models into the linkgraph package.

### D6: Lazy import of linkgraph in CLI commands

Following the established pattern in `lexi_app.py`, all linkgraph imports happen inside command functions (lazy imports). This keeps CLI startup fast and avoids importing `sqlite3` when the index is not needed.

## Risks / Trade-offs

- **[Stale index data]** The index may not reflect the latest state of the library if `lexictl update` has not run recently. Agents may see outdated reverse links. -> Mitigation: `lexi lookup` already warns about staleness via source_hash comparison. The index staleness is an accepted trade-off documented in the master plan (D-070). `lexictl status` (Phase 10f) will report index age.

- **[FTS ranking quality]** FTS5's BM25 ranking depends on the quality of the indexed text (title + body from the builder). Poor body extraction in the builder could degrade search relevance. -> Mitigation: This is a builder concern (10b), not a CLI concern. The CLI just passes through whatever the FTS5 engine ranks.

- **[Performance of file-scanning fallback]** The fallback path for tag search still scans all files, which is O(N). For large projects without an index, this could be slow. -> Mitigation: This is the existing behavior (pre-10e). The index is the solution, not a regression.

- **[Display clutter in lookup]** Adding reverse links to `lookup` output increases output length. For highly-connected files, the list could be long. -> Mitigation: Consider capping displayed reverse links (e.g., show first 20 with "and N more..."). This can be tuned post-implementation.
