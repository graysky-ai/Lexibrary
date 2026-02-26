## MODIFIED Requirements

### Requirement: Serialize AIndexFile to v2 markdown format
The system SHALL provide a `serialize_aindex(data: AIndexFile) -> str` function in `src/lexibrary/artifacts/aindex_serializer.py` that converts an `AIndexFile` Pydantic model into a v2 `.aindex` markdown string.

The output format SHALL follow these rules:
1. H1 heading = `directory_path` with trailing `/`
2. Blank line after H1, after billboard, and after each section
3. Child Map section is a 3-column markdown table: `Name`, `Type`, `Description`
4. Entries sorted: files first (case-insensitive alphabetical), then directories (case-insensitive alphabetical)
5. File names wrapped in backticks; directory names have trailing `/` and backticks
6. `Type` column: `file` or `dir`
7. Empty Child Map shows `(none)` instead of a table
8. Staleness metadata as an HTML comment footer: `<!-- lexibrary:meta ... -->`
9. Output ends with a single trailing newline

The output SHALL NOT contain a `## Local Conventions` section.

#### Scenario: Serialize basic directory with files and subdirs
- **WHEN** `serialize_aindex()` is called with an `AIndexFile` containing one file entry and one dir entry
- **THEN** the output SHALL contain the H1 heading, billboard, Child Map table with both entries (file first, then dir), and metadata footer. No Local Conventions section SHALL be present.

#### Scenario: Serialize empty directory
- **WHEN** `serialize_aindex()` is called with an `AIndexFile` with no entries
- **THEN** the Child Map section SHALL show `(none)`. No Local Conventions section SHALL be present.

#### Scenario: Entries sorted files before dirs
- **WHEN** `serialize_aindex()` is called with entries in random order
- **THEN** the output Child Map SHALL have all file entries before all dir entries, each group sorted case-insensitively

#### Scenario: Metadata footer serialized as HTML comment
- **WHEN** `serialize_aindex()` is called with a `StalenessMetadata` in the model
- **THEN** the output SHALL end with `<!-- lexibrary:meta` ... `-->` containing source, source_hash, generated, and generator fields

#### Scenario: Output ends with trailing newline
- **WHEN** `serialize_aindex()` is called with any valid input
- **THEN** the returned string SHALL end with `\n`

#### Scenario: No Local Conventions section in output
- **WHEN** `serialize_aindex()` is called with any valid input
- **THEN** the output SHALL NOT contain the text `## Local Conventions`

