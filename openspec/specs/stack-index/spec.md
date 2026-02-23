# stack-index Specification

## Purpose
TBD - created by archiving change the-stack. Update Purpose after archive.
## Requirements
### Requirement: StackIndex class
The system SHALL provide a `StackIndex` class in `src/lexibrary/stack/index.py` with a `build(cls, project_root: Path) -> StackIndex` classmethod that scans the `.lexibrary/stack/` directory, parses each `ST-NNN-*.md` file, and builds an in-memory searchable index.

#### Scenario: Build index from stack directory
- **WHEN** `StackIndex.build(project_root)` is called and `.lexibrary/stack/` contains 3 post files
- **THEN** the index SHALL contain 3 `StackPost` objects

#### Scenario: Build index with empty stack directory
- **WHEN** `StackIndex.build(project_root)` is called and `.lexibrary/stack/` is empty
- **THEN** the index SHALL contain 0 posts

#### Scenario: Build index skips malformed files
- **WHEN** `.lexibrary/stack/` contains a malformed file
- **THEN** the index SHALL skip it and include only valid posts

### Requirement: Full-text search
The `StackIndex` SHALL provide a `search(self, query: str) -> list[StackPost]` method that performs case-insensitive substring matching across post titles, problem descriptions, answer bodies, and tags. Results SHALL be returned sorted by vote count descending.

#### Scenario: Search matches title
- **WHEN** `index.search("timezone")` is called and a post has "timezone" in its title
- **THEN** the post SHALL be included in results

#### Scenario: Search matches problem body
- **WHEN** `index.search("datetime.now")` is called and a post has "datetime.now" in its problem section
- **THEN** the post SHALL be included in results

#### Scenario: Search matches answer body
- **WHEN** `index.search("utils/time.py")` is called and a post has this text in an answer
- **THEN** the post SHALL be included in results

#### Scenario: Search matches tags
- **WHEN** `index.search("data-integrity")` is called and a post has that tag
- **THEN** the post SHALL be included in results

#### Scenario: Search is case-insensitive
- **WHEN** `index.search("TIMEZONE")` is called
- **THEN** it SHALL return the same results as `index.search("timezone")`

#### Scenario: Search returns no matches
- **WHEN** `index.search("nonexistent-query-xyz")` is called
- **THEN** it SHALL return an empty list

### Requirement: Filter by tag
The `StackIndex` SHALL provide a `by_tag(self, tag: str) -> list[StackPost]` method that filters posts by tag (case-insensitive).

#### Scenario: Filter by existing tag
- **WHEN** `index.by_tag("datetime")` is called and 2 posts have the "datetime" tag
- **THEN** the result SHALL contain exactly 2 posts

#### Scenario: Filter by nonexistent tag
- **WHEN** `index.by_tag("nonexistent")` is called
- **THEN** the result SHALL be an empty list

### Requirement: Filter by scope
The `StackIndex` SHALL provide a `by_scope(self, path: str) -> list[StackPost]` method that filters posts by referenced file path using prefix matching (e.g., `src/models/` matches `src/models/event.py`).

#### Scenario: Filter by directory scope
- **WHEN** `index.by_scope("src/models/")` is called and a post references `src/models/event.py`
- **THEN** the post SHALL be included in results

#### Scenario: Filter by exact file scope
- **WHEN** `index.by_scope("src/models/event.py")` is called
- **THEN** only posts referencing that exact file SHALL be returned

### Requirement: Filter by status
The `StackIndex` SHALL provide a `by_status(self, status: str) -> list[StackPost]` method that filters posts by status.

#### Scenario: Filter open posts
- **WHEN** `index.by_status("open")` is called
- **THEN** only posts with `status="open"` SHALL be returned

### Requirement: Filter by concept
The `StackIndex` SHALL provide a `by_concept(self, concept: str) -> list[StackPost]` method that filters posts referencing a specific concept name (case-insensitive).

#### Scenario: Filter by concept name
- **WHEN** `index.by_concept("DateHandling")` is called and a post has `refs.concepts=["DateHandling"]`
- **THEN** the post SHALL be included in results

