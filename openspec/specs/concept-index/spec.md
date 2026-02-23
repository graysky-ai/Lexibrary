# concept-index Specification

## Purpose
TBD - created by archiving change concepts-wiki. Update Purpose after archive.
## Requirements
### Requirement: ConceptIndex class
The system SHALL provide a `ConceptIndex` class in `src/lexibrary/wiki/index.py` that:
- Is constructed with `concepts_dir: Path` pointing to `.lexibrary/concepts/`
- Provides `load() -> None` that scans the directory and parses all `.md` files into `ConceptFile` objects
- Stores parsed concepts in a `concepts: list[ConceptFile]` attribute

#### Scenario: Load concepts from directory
- **WHEN** `ConceptIndex(concepts_dir).load()` is called on a directory with 3 valid concept files
- **THEN** `index.concepts` SHALL contain 3 `ConceptFile` objects

#### Scenario: Load empty directory
- **WHEN** `ConceptIndex(concepts_dir).load()` is called on an empty directory
- **THEN** `index.concepts` SHALL be an empty list

#### Scenario: Load skips malformed files
- **WHEN** `ConceptIndex(concepts_dir).load()` is called on a directory with 2 valid and 1 malformed concept file
- **THEN** `index.concepts` SHALL contain 2 `ConceptFile` objects (malformed file skipped)

### Requirement: Search concepts
The `ConceptIndex` SHALL provide `search(query: str) -> list[ConceptFile]` that returns concepts matching the query against name, aliases, tags, and summary using case-insensitive normalized substring matching (lowercase, strip hyphens/underscores/spaces).

#### Scenario: Search by name
- **WHEN** `index.search("jwt")` is called and a concept named "JWT Auth" exists
- **THEN** the result SHALL include the "JWT Auth" concept

#### Scenario: Search by alias
- **WHEN** `index.search("json web token")` is called and a concept has alias "json-web-token"
- **THEN** the result SHALL include that concept

#### Scenario: Search by tag
- **WHEN** `index.search("auth")` is called and a concept has tag "auth"
- **THEN** the result SHALL include that concept

#### Scenario: Search no results
- **WHEN** `index.search("nonexistent")` is called and no concepts match
- **THEN** the result SHALL be an empty list

### Requirement: Find concept by exact name
The `ConceptIndex` SHALL provide `find(name: str) -> ConceptFile | None` that returns a concept matching by exact title (case-insensitive) or by exact alias (case-insensitive). Returns `None` if no match.

#### Scenario: Find by exact name
- **WHEN** `index.find("JWT Auth")` is called
- **THEN** it SHALL return the concept with title "JWT Auth"

#### Scenario: Find by alias
- **WHEN** `index.find("json-web-token")` is called and a concept has that alias
- **THEN** it SHALL return that concept

#### Scenario: Find case insensitive
- **WHEN** `index.find("jwt auth")` is called and a concept is titled "JWT Auth"
- **THEN** it SHALL return that concept

#### Scenario: Find no match
- **WHEN** `index.find("Nonexistent")` is called
- **THEN** it SHALL return `None`

### Requirement: List concept names
The `ConceptIndex` SHALL provide `names() -> list[str]` that returns a sorted list of all concept titles.

#### Scenario: List names
- **WHEN** `index.names()` is called after loading 3 concepts
- **THEN** it SHALL return a sorted list of 3 concept title strings

### Requirement: Filter by tag
The `ConceptIndex` SHALL provide `by_tag(tag: str) -> list[ConceptFile]` that returns all concepts having the specified tag (case-insensitive comparison).

#### Scenario: Filter by tag
- **WHEN** `index.by_tag("auth")` is called and 2 of 5 concepts have the "auth" tag
- **THEN** the result SHALL contain exactly those 2 concepts

#### Scenario: Filter by tag no matches
- **WHEN** `index.by_tag("nonexistent")` is called
- **THEN** the result SHALL be an empty list

