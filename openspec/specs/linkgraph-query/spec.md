# linkgraph-query Specification

## Purpose
TBD - created by archiving change phase-10c-linkgraph-query. Update Purpose after archive.
## Requirements
### Requirement: LinkGraph.open() factory with graceful degradation
The system SHALL provide a `LinkGraph.open(db_path)` classmethod that returns a `LinkGraph` instance or `None`. It MUST return `None` when the database file does not exist, when the file is corrupt (raises `sqlite3.DatabaseError`), or when the schema version does not match `SCHEMA_VERSION`. When opening successfully, it MUST call `set_pragmas()` on the connection and open in read-only mode.

#### Scenario: Database file does not exist
- **WHEN** `LinkGraph.open()` is called with a path to a non-existent file
- **THEN** it SHALL return `None` without raising an exception

#### Scenario: Database file is corrupt
- **WHEN** `LinkGraph.open()` is called with a path to a corrupt SQLite file
- **THEN** it SHALL catch `sqlite3.DatabaseError` and return `None`

#### Scenario: Schema version mismatch
- **WHEN** `LinkGraph.open()` is called and `check_schema_version()` returns a value different from `SCHEMA_VERSION`
- **THEN** it SHALL return `None`

#### Scenario: Schema version missing
- **WHEN** `LinkGraph.open()` is called and `check_schema_version()` returns `None`
- **THEN** it SHALL return `None`

#### Scenario: Successful open
- **WHEN** `LinkGraph.open()` is called with a valid database with matching schema version
- **THEN** it SHALL return a `LinkGraph` instance with WAL pragmas applied and the connection opened in read-only mode

### Requirement: LinkGraph as context manager
The `LinkGraph` class SHALL implement `__enter__` and `__exit__` for use as a context manager. It SHALL also provide an explicit `close()` method. On exit or close, the underlying SQLite connection MUST be closed.

#### Scenario: Used as context manager
- **WHEN** a `LinkGraph` instance is used in a `with` statement
- **THEN** the connection SHALL be open inside the block and closed after the block exits

#### Scenario: Explicit close
- **WHEN** `close()` is called on a `LinkGraph` instance
- **THEN** the underlying SQLite connection SHALL be closed

### Requirement: Reverse dependency lookup
The system SHALL provide a method `reverse_deps(path, link_type=None)` that returns all artifacts that reference the given artifact. The method MUST accept an optional `link_type` filter. Results SHALL be returned as a list of `LinkResult` dataclasses.

#### Scenario: Find all importers of a source file
- **WHEN** `reverse_deps("src/auth/service.py", link_type="ast_import")` is called
- **THEN** it SHALL return a list of `LinkResult` entries for every artifact that has an `ast_import` link targeting that file

#### Scenario: Find all references to a concept
- **WHEN** `reverse_deps("concepts/Authentication.md")` is called with no `link_type` filter
- **THEN** it SHALL return all inbound links regardless of type (wikilinks, stack refs, convention refs)

#### Scenario: Artifact not found in index
- **WHEN** `reverse_deps()` is called for a path that has no artifact row
- **THEN** it SHALL return an empty list

### Requirement: Tag search
The system SHALL provide a method `search_by_tag(tag)` that queries the `tags` table and returns all matching artifacts. Results SHALL be returned as a list of `ArtifactResult` dataclasses.

#### Scenario: Tag exists with matches
- **WHEN** `search_by_tag("authentication")` is called and artifacts have that tag
- **THEN** it SHALL return `ArtifactResult` entries for each matching artifact with path, kind, and title

#### Scenario: Tag has no matches
- **WHEN** `search_by_tag("nonexistent-tag")` is called
- **THEN** it SHALL return an empty list

### Requirement: Full-text search
The system SHALL provide a method `full_text_search(query, limit=20)` that queries the `artifacts_fts` FTS5 table. Results SHALL be returned as a list of `ArtifactResult` dataclasses ordered by FTS5 rank. The search term MUST be sanitized to prevent FTS syntax errors by quoting literal terms.

#### Scenario: Matching results exist
- **WHEN** `full_text_search("authentication token")` is called
- **THEN** it SHALL return up to `limit` `ArtifactResult` entries ordered by relevance rank

#### Scenario: No matching results
- **WHEN** `full_text_search("xyznonexistent")` is called
- **THEN** it SHALL return an empty list

#### Scenario: Search term with special FTS characters
- **WHEN** `full_text_search("error OR warning")` is called (containing FTS operators)
- **THEN** it SHALL treat the input as a literal phrase (double-quoted) and not raise an FTS syntax error

### Requirement: Alias resolution
The system SHALL provide a method `resolve_alias(alias)` that queries the `aliases` table with case-insensitive matching. It SHALL return an `ArtifactResult` or `None`.

#### Scenario: Alias matches a concept
- **WHEN** `resolve_alias("auth")` is called and a concept has "auth" as an alias
- **THEN** it SHALL return the `ArtifactResult` for that concept

#### Scenario: Case-insensitive matching
- **WHEN** `resolve_alias("AUTH")` is called and the stored alias is "auth"
- **THEN** it SHALL match case-insensitively and return the `ArtifactResult`

#### Scenario: No matching alias
- **WHEN** `resolve_alias("nonexistent")` is called
- **THEN** it SHALL return `None`

### Requirement: Convention inheritance
The system SHALL provide a method `get_conventions(directory_paths)` that retrieves conventions for a list of directory paths (ordered from root to leaf). Results SHALL be returned as a list of `ConventionResult` dataclasses ordered by directory path and then ordinal.

#### Scenario: Conventions exist for ancestor directories
- **WHEN** `get_conventions(["src", "src/auth", "src/auth/middleware"])` is called
- **THEN** it SHALL return all conventions for those directories ordered by path depth then ordinal

#### Scenario: No conventions for any path
- **WHEN** `get_conventions(["nonexistent/path"])` is called
- **THEN** it SHALL return an empty list

### Requirement: Build summary
The system SHALL provide a method `build_summary()` that returns aggregate statistics for the most recent build in `build_log`. Results SHALL be returned as a list of `BuildSummaryEntry` dataclasses. If no build log entries exist, it SHALL return an empty list.

#### Scenario: Build log has entries
- **WHEN** `build_summary()` is called and the build log has entries
- **THEN** it SHALL return one `BuildSummaryEntry` per action type (created, updated, deleted, unchanged, failed) for the most recent build, with count and total duration

#### Scenario: Build log is empty
- **WHEN** `build_summary()` is called and the build log has no entries
- **THEN** it SHALL return an empty list

### Requirement: Multi-hop graph traversal
The system SHALL provide a method `traverse(start_path, max_depth=3, link_types=None, direction="outbound")` that performs recursive graph traversal using a recursive CTE. The `max_depth` parameter MUST be capped at a hard maximum of 10. The traversal MUST handle cyclic graphs without infinite recursion by tracking visited nodes in the CTE. Results SHALL be returned as a list of `TraversalNode` dataclasses.

#### Scenario: Outbound traversal of import chain
- **WHEN** `traverse("src/api/controller.py", max_depth=2, link_types=["ast_import"], direction="outbound")` is called
- **THEN** it SHALL return `TraversalNode` entries for all transitively imported files up to depth 2, each with their depth level

#### Scenario: Inbound traversal (reverse dependency chain)
- **WHEN** `traverse("src/core/utils.py", max_depth=3, direction="inbound")` is called
- **THEN** it SHALL return `TraversalNode` entries for all artifacts that transitively reference the target, up to depth 3

#### Scenario: Cyclic graph does not cause infinite recursion
- **WHEN** `traverse()` encounters a cycle (A imports B, B imports A)
- **THEN** it SHALL terminate without revisiting already-visited nodes and return finite results

#### Scenario: max_depth exceeds hard cap
- **WHEN** `traverse(start_path, max_depth=50)` is called
- **THEN** it SHALL clamp max_depth to 10

#### Scenario: Start path not found
- **WHEN** `traverse()` is called with a path that has no artifact row
- **THEN** it SHALL return an empty list

### Requirement: Structured result types
All query methods SHALL return results as dataclass instances, not raw tuples or dictionaries. The module SHALL define: `ArtifactResult`, `LinkResult`, `TraversalNode`, `ConventionResult`, and `BuildSummaryEntry`.

#### Scenario: Result type fields accessible by name
- **WHEN** a query method returns an `ArtifactResult`
- **THEN** its fields (id, path, kind, title, status) SHALL be accessible as named attributes

#### Scenario: Result types support equality comparison
- **WHEN** two `ArtifactResult` instances have identical field values
- **THEN** they SHALL be equal via `==`

### Requirement: Read-only enforcement
The `LinkGraph` class SHALL open the SQLite connection in read-only mode using URI syntax (`?mode=ro`). No method on `LinkGraph` SHALL execute INSERT, UPDATE, DELETE, or DDL statements.

#### Scenario: Attempt to write via the connection
- **WHEN** code attempts a write operation through the `LinkGraph` connection
- **THEN** SQLite SHALL raise an `OperationalError` due to read-only mode

### Requirement: Public API export
The `linkgraph/__init__.py` module SHALL export the `LinkGraph` class and all result dataclasses in its `__all__` list.

#### Scenario: Import from package
- **WHEN** code executes `from lexibrarian.linkgraph import LinkGraph`
- **THEN** the import SHALL succeed and `LinkGraph` SHALL be the query class from `query.py`

### Requirement: Parameterized queries
All SQL queries in the `LinkGraph` class MUST use parameterized statements with `?` placeholders. No query SHALL use string formatting or f-strings to interpolate values into SQL.

#### Scenario: Path with special characters
- **WHEN** a query method is called with a path containing single quotes or other SQL-special characters
- **THEN** the query SHALL execute correctly without SQL errors due to parameterized binding

### Requirement: Artifact lookup by path
The system SHALL provide a method `get_artifact(path)` that returns the `ArtifactResult` for a given path, or `None` if the path is not in the index.

#### Scenario: Artifact exists
- **WHEN** `get_artifact("src/auth/service.py")` is called and the artifact is indexed
- **THEN** it SHALL return the `ArtifactResult` with all fields populated

#### Scenario: Artifact does not exist
- **WHEN** `get_artifact("nonexistent.py")` is called
- **THEN** it SHALL return `None`

