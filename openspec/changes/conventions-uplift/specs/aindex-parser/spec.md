## MODIFIED Requirements

### Requirement: Parse v2 .aindex file into AIndexFile model
The system SHALL provide a `parse_aindex(path: Path) -> AIndexFile | None` function in `src/lexibrary/artifacts/aindex_parser.py` that reads a `.aindex` file and returns an `AIndexFile` Pydantic model.

The parser SHALL:
- Extract the `directory_path` from the H1 heading (strip trailing `/`)
- Extract the billboard from text between H1 and first H2 section
- Parse Child Map table rows into `AIndexEntry` objects with correct `entry_type`
- Parse the metadata HTML comment footer into a `StalenessMetadata` model
- Return `None` if the file does not exist or content is malformed beyond recovery
- Be tolerant of minor whitespace differences (extra blank lines, trailing spaces)
- Silently ignore any `## Local Conventions` section if encountered in legacy files (do not error, do not populate any field)

The parser SHALL NOT populate a `local_conventions` field (the field no longer exists on `AIndexFile`).

#### Scenario: Parse well-formed .aindex file
- **WHEN** `parse_aindex()` is called with a path to a valid v2 `.aindex` file
- **THEN** it SHALL return an `AIndexFile` with directory_path, billboard, entries, and metadata correctly populated

#### Scenario: Parse returns None for nonexistent file
- **WHEN** `parse_aindex()` is called with a path to a file that does not exist
- **THEN** it SHALL return `None`

#### Scenario: Parse returns None for malformed content
- **WHEN** `parse_aindex()` is called with a file containing garbage content (no recognizable sections)
- **THEN** it SHALL return `None`

#### Scenario: Parse handles empty Child Map
- **WHEN** `parse_aindex()` is called with a file where Child Map shows `(none)`
- **THEN** it SHALL return an `AIndexFile` with `entries=[]`

#### Scenario: Parse extracts metadata footer
- **WHEN** `parse_aindex()` is called with a file containing a `<!-- lexibrary:meta ... -->` footer
- **THEN** the returned model's `metadata` SHALL have the correct `source`, `source_hash`, `generated`, and `generator` fields

#### Scenario: Parse tolerates legacy Local Conventions section
- **WHEN** `parse_aindex()` is called with a file that still contains a `## Local Conventions` section
- **THEN** it SHALL parse successfully, ignoring the conventions section

## REMOVED Requirements

### Requirement: Parse extracts local conventions
**Reason**: The `local_conventions` field has been removed from `AIndexFile` (D9). Conventions are now stored as standalone files in `.lexibrary/conventions/`.
**Migration**: Conventions are managed via `lexi convention new` and retrieved via `ConventionIndex`. The parser no longer extracts convention data from `.aindex` files.
