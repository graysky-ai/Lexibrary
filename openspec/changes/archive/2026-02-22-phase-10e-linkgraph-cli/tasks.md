## 1. Linkgraph Module Exports

- [x] 1.1 Add `open_index` re-export to `src/lexibrarian/linkgraph/__init__.py` so CLI code can `from lexibrarian.linkgraph import open_index`
- [x] 1.2 Verify `open_index(project_root)` returns `LinkGraph | None` from `query.py` (Phase 10c prerequisite -- confirm the function exists and its signature)

## 2. Reverse Links in `lexi lookup`

- [x] 2.1 In `lexi_app.py` `lookup` command, add lazy import of `open_index` and call it after the conventions section to get a `LinkGraph | None`
- [x] 2.2 When `LinkGraph` is available, query `reverse_deps(file_path)` for inbound `ast_import` links and display `## Dependents (imports this file)` section with bullet list of source paths
- [x] 2.3 When `LinkGraph` is available, query `references_to(file_path)` for all other inbound link types and display `## Also Referenced By` section with annotated entries (e.g. `[[Authentication]] (concept wikilink)`)
- [x] 2.4 Ensure both sections are silently omitted when `open_index()` returns `None` (graceful degradation)
- [x] 2.5 Ensure both sections are silently omitted when the file has no inbound links

## 3. Index-Accelerated Tag Search in `unified_search()`

- [x] 3.1 Add `link_graph: LinkGraph | None = None` parameter to the `unified_search()` function signature in `search.py`
- [x] 3.2 Implement index-accelerated tag search path: when `link_graph` is not `None` and `tag` is provided, call `link_graph.search_tag(tag)` and map results to `SearchResults` grouped by artifact kind
- [x] 3.3 Preserve existing file-scanning tag search as fallback when `link_graph` is `None`
- [x] 3.4 Apply scope filter on top of index-accelerated tag results when both `--tag` and `--scope` are provided

## 4. FTS Full-Text Search in `unified_search()`

- [x] 4.1 Implement FTS search path: when `link_graph` is not `None` and `query` is provided (without `tag`), call `link_graph.search_fts(query)` and map results to `SearchResults` grouped by artifact kind
- [x] 4.2 Preserve existing file-scanning free-text search as fallback when `link_graph` is `None`
- [x] 4.3 Ensure FTS results include title metadata from the artifacts table for display without extra file I/O

## 5. Wire `open_index` into the `search` CLI Command

- [x] 5.1 In `lexi_app.py` `search` command, add lazy import of `open_index` and call it to get `LinkGraph | None`
- [x] 5.2 Pass the `LinkGraph` instance (or `None`) to `unified_search()` via the new `link_graph` parameter

## 6. Tests

- [x] 6.1 Write tests for `lexi lookup` reverse link display: file with dependents, file with cross-references, file with both, file with no inbound links
- [x] 6.2 Write tests for `lexi lookup` graceful degradation: index missing, index corrupt, schema version mismatch
- [x] 6.3 Write tests for `unified_search()` with `link_graph` parameter: tag search with index, tag search fallback without index
- [x] 6.4 Write tests for `unified_search()` FTS path: FTS search with index, free-text fallback without index
- [x] 6.5 Write tests for `lexi search` CLI command dispatching `open_index()` to `unified_search()`
- [x] 6.6 Write tests for tag + scope combined filter with index-accelerated path

## 7. Blueprint Updates

- [x] 7.1 Update `blueprints/src/lexibrarian/cli/lexi_app.md` to document reverse link display in `lookup` and `open_index` usage in `search`
- [x] 7.2 Update `blueprints/src/lexibrarian/search.md` to document the `link_graph` parameter and dual code paths
- [x] 7.3 Update `blueprints/src/lexibrarian/linkgraph/` (create or update design file for `__init__.py`) to document `open_index` re-export
