# aindex-parser Specification

## Purpose
TBD - created by archiving change directory-indexes. Update Purpose after archive.
## Requirements
### Requirement: Parse v2 .aindex file into AIndexFile model
The system SHALL provide a `parse_aindex(path: Path) -> AIndexFile | None` function in `src/lexibrary/artifacts/aindex_parser.py` that reads a `.aindex` file and returns an `AIndexFile` Pydantic model.

The parser SHALL:
- Extract the `directory_path` from the H1 heading (strip trailing `/`)
- Extract the billboard from text between H1 and first H2 section
- Parse Child Map table rows into `AIndexEntry` objects with correct `entry_type`
- Parse Local Conventions as a list of strings (strip `- ` bullet prefix)
- Parse the metadata HTML comment footer into a `StalenessMetadata` model
- Return `None` if the file does not exist or content is malformed beyond recovery
- Be tolerant of minor whitespace differences (extra blank lines, trailing spaces)

#### Scenario: Parse well-formed .aindex file
- **WHEN** `parse_aindex()` is called with a path to a valid v2 `.aindex` file
- **THEN** it SHALL return an `AIndexFile` with all fields correctly populated

#### Scenario: Parse returns None for nonexistent file
- **WHEN** `parse_aindex()` is called with a path to a file that does not exist
- **THEN** it SHALL return `None`

#### Scenario: Parse returns None for malformed content
- **WHEN** `parse_aindex()` is called with a file containing garbage content (no recognizable sections)
- **THEN** it SHALL return `None`

#### Scenario: Parse handles empty sections
- **WHEN** `parse_aindex()` is called with a file where Child Map shows `(none)` and Local Conventions shows `(none)`
- **THEN** it SHALL return an `AIndexFile` with `entries=[]` and `local_conventions=[]`

#### Scenario: Parse extracts local conventions
- **WHEN** `parse_aindex()` is called with a file containing Local Conventions bullet items
- **THEN** the returned model's `local_conventions` SHALL contain those items as plain strings (without bullet prefix)

#### Scenario: Parse extracts metadata footer
- **WHEN** `parse_aindex()` is called with a file containing a `<!-- lexibrary:meta ... -->` footer
- **THEN** the returned model's `metadata` SHALL have the correct `source`, `source_hash`, `generated`, and `generator` fields

### Requirement: Parse metadata-only from .aindex file
The system SHALL provide a `parse_aindex_metadata(path: Path) -> StalenessMetadata | None` function in `src/lexibrary/artifacts/aindex_parser.py` that reads only the HTML comment metadata footer from a `.aindex` file.

The function SHALL be cheaper than `parse_aindex()` — it reads only as much of the file as needed to extract the footer, avoiding full parsing of the table and sections.

#### Scenario: Parse metadata from valid file
- **WHEN** `parse_aindex_metadata()` is called with a path to a valid `.aindex` file
- **THEN** it SHALL return a `StalenessMetadata` with correct field values

#### Scenario: Parse metadata returns None for missing file
- **WHEN** `parse_aindex_metadata()` is called with a nonexistent path
- **THEN** it SHALL return `None`

#### Scenario: Parse metadata standalone
- **WHEN** `parse_aindex_metadata()` is called without calling `parse_aindex()` first
- **THEN** it SHALL work independently and return the same `StalenessMetadata` as calling `parse_aindex()` would return

