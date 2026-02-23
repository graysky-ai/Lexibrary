# search

**Summary:** Unified cross-artifact search across concepts, design files, and Stack posts — powers `lexi search`.

## Interface

| Name | Key Fields / Signature | Purpose |
| --- | --- | --- |
| `SearchResults` | `concepts`, `design_files`, `stack_posts` | Container for grouped search results across artifact types |
| `SearchResults.has_results` | `() -> bool` | True if any group has results |
| `SearchResults.render` | `(console: Console) -> None` | Render grouped results as Rich tables |
| `unified_search` | `(project_root, *, query?, tag?, scope?, link_graph?) -> SearchResults` | Search across all artifact types; uses index-accelerated path when `link_graph` is provided, file-scanning fallback otherwise |

## Internal Functions

| Name | Purpose |
| --- | --- |
| `_tag_search_from_index` | Index-accelerated tag search via `link_graph.search_by_tag()`; groups `ArtifactResult` hits by kind (`concept`, `design`, `stack`) into `SearchResults`; applies scope filter (concepts omitted when scope is active) |
| `_fts_search` | FTS5-accelerated free-text search via `link_graph.full_text_search()`; groups results by artifact kind with title metadata from the `artifacts` table (no extra file I/O); applies scope filter |
| `_search_concepts` | File-scanning fallback: search concepts via `ConceptIndex`; supports query and tag filters; scope filter returns empty (concepts are not file-scoped) |
| `_search_design_files` | File-scanning fallback: scan `.lexibrary/*.md` (excluding `concepts/`, `stack/`, `START_HERE.md`, `HANDOFF.md`); filter by scope, tag, and free-text query against description + source_path + tags |
| `_search_stack_posts` | File-scanning fallback: search Stack posts via `StackIndex`; supports query, tag, and scope filters |

## Dependencies

- `lexibrary.linkgraph.query` -- `LinkGraph` (TYPE_CHECKING import for type annotations)
- `lexibrary.wiki.index` -- `ConceptIndex` (lazy import in file-scanning fallback)
- `lexibrary.artifacts.design_file_parser` -- `parse_design_file` (lazy import in file-scanning fallback)
- `lexibrary.stack.index` -- `StackIndex` (lazy import in file-scanning fallback)

## Dependents

- `lexibrary.cli` -- `search` command calls `unified_search()`

## Key Concepts

- `unified_search()` has three code paths selected by the combination of `link_graph` and filter parameters:
  1. **Index-accelerated tag search:** when `link_graph is not None` and `tag` is provided, delegates to `_tag_search_from_index()` which calls `link_graph.search_by_tag()` -- O(1) tag lookup via the SQLite `tags` table
  2. **FTS-accelerated free-text search:** when `link_graph is not None` and `query` is provided (without `tag`), delegates to `_fts_search()` which calls `link_graph.full_text_search()` for relevance-ranked results; title metadata comes directly from the `artifacts` table, avoiding extra file I/O
  3. **File-scanning fallback:** when `link_graph is None`, scans artifact files on disk via `_search_concepts()`, `_search_design_files()`, and `_search_stack_posts()`
- Scope filter is applied on top of index-accelerated results when both `--tag` and `--scope` are provided; concepts are omitted when scope is active (they are not file-scoped)
- All three search backends are independent -- results are grouped by type, not interleaved
- Rich rendering: each result type gets its own table with type-appropriate columns and color-coded status badges
