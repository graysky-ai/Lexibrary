## 1. Result Dataclasses

- [x] 1.1 Define `ArtifactResult` dataclass with fields: id, path, kind, title, status
- [x] 1.2 Define `LinkResult` dataclass with fields: source_id, source_path, link_type, link_context
- [x] 1.3 Define `TraversalNode` dataclass with fields: artifact_id, path, kind, depth, via_link_type
- [x] 1.4 Define `ConventionResult` dataclass with fields: body, directory_path, ordinal
- [x] 1.5 Define `BuildSummaryEntry` dataclass with fields: action, count, total_duration_ms

## 2. LinkGraph Core (open, close, context manager)

- [x] 2.1 Implement `LinkGraph.__init__()` accepting an open `sqlite3.Connection`
- [x] 2.2 Implement `LinkGraph.open(db_path)` classmethod returning `LinkGraph | None` with graceful degradation (missing file, corrupt DB, schema mismatch)
- [x] 2.3 Open connection in read-only mode using URI syntax (`file:{path}?mode=ro`)
- [x] 2.4 Apply `set_pragmas()` on successful connection open
- [x] 2.5 Implement `close()` method to close the underlying connection
- [x] 2.6 Implement `__enter__` and `__exit__` for context manager support

## 3. Single-Entity Queries

- [x] 3.1 Implement `get_artifact(path)` returning `ArtifactResult | None`
- [x] 3.2 Implement `resolve_alias(alias)` returning `ArtifactResult | None` with case-insensitive matching

## 4. Relationship Queries

- [x] 4.1 Implement `reverse_deps(path, link_type=None)` returning `list[LinkResult]` for all inbound links to an artifact
- [x] 4.2 Implement `search_by_tag(tag)` returning `list[ArtifactResult]` via join on tags table
- [x] 4.3 Implement `full_text_search(query, limit=20)` returning `list[ArtifactResult]` via FTS5 MATCH with literal quoting for safety
- [x] 4.4 Implement `get_conventions(directory_paths)` returning `list[ConventionResult]` ordered by path then ordinal
- [x] 4.5 Implement `build_summary()` returning `list[BuildSummaryEntry]` for the most recent build

## 5. Multi-Hop Traversal

- [x] 5.1 Implement `traverse(start_path, max_depth=3, link_types=None, direction="outbound")` using recursive CTE
- [x] 5.2 Clamp `max_depth` to hard cap of 10
- [x] 5.3 Add cycle detection via visited-node tracking in the CTE to prevent infinite recursion
- [x] 5.4 Support `direction="inbound"` (reverse traversal) and `direction="outbound"` (forward traversal)
- [x] 5.5 Support optional `link_types` filter to restrict traversal to specific edge types

## 6. Public API Export

- [x] 6.1 Update `src/lexibrarian/linkgraph/__init__.py` to import and export `LinkGraph` and all result dataclasses in `__all__`

## 7. Tests

- [x] 7.1 Write tests for `LinkGraph.open()` graceful degradation: missing file returns `None`
- [x] 7.2 Write tests for `LinkGraph.open()` graceful degradation: corrupt file returns `None`
- [x] 7.3 Write tests for `LinkGraph.open()` graceful degradation: schema version mismatch returns `None`
- [x] 7.4 Write tests for `LinkGraph.open()` successful open and context manager close
- [x] 7.5 Write tests for `get_artifact()` with existing and non-existing paths
- [x] 7.6 Write tests for `reverse_deps()` with and without link_type filter
- [x] 7.7 Write tests for `search_by_tag()` with matching and non-matching tags
- [x] 7.8 Write tests for `full_text_search()` including special character handling
- [x] 7.9 Write tests for `resolve_alias()` with case-insensitive matching
- [x] 7.10 Write tests for `get_conventions()` with multiple directory paths
- [x] 7.11 Write tests for `build_summary()` with and without log entries
- [x] 7.12 Write tests for `traverse()` outbound and inbound directions
- [x] 7.13 Write tests for `traverse()` cycle detection (A->B->A does not loop)
- [x] 7.14 Write tests for `traverse()` max_depth clamping to 10
- [x] 7.15 Write tests for read-only enforcement (write attempt raises OperationalError)
- [x] 7.16 Run full test suite (`uv run pytest --cov=lexibrarian`), lint (`uv run ruff check src/ tests/`), and type check (`uv run mypy src/`)
