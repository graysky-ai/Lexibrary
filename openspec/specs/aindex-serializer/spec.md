# aindex-serializer Specification

## Purpose
TBD - created by archiving change directory-indexes. Update Purpose after archive.
## Requirements
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
8. Local Conventions section always present — empty renders as `(none)`, non-empty renders as bullet list
9. Staleness metadata as an HTML comment footer: `<!-- lexibrary:meta ... -->`
10. Output ends with a single trailing newline

#### Scenario: Serialize basic directory with files and subdirs
- **WHEN** `serialize_aindex()` is called with an `AIndexFile` containing one file entry and one dir entry
- **THEN** the output SHALL contain the H1 heading, billboard, Child Map table with both entries (file first, then dir), Local Conventions section, and metadata footer

#### Scenario: Serialize empty directory
- **WHEN** `serialize_aindex()` is called with an `AIndexFile` with no entries
- **THEN** both Child Map and Local Conventions sections SHALL show `(none)`

#### Scenario: Serialize files-only directory
- **WHEN** `serialize_aindex()` is called with an `AIndexFile` containing only file entries
- **THEN** the Child Map table SHALL list all files with no dir rows

#### Scenario: Serialize dirs-only directory
- **WHEN** `serialize_aindex()` is called with an `AIndexFile` containing only dir entries
- **THEN** the Child Map table SHALL list all dirs with no file rows

#### Scenario: Entries sorted files before dirs
- **WHEN** `serialize_aindex()` is called with entries in random order
- **THEN** the output Child Map SHALL have all file entries before all dir entries, each group sorted case-insensitively

#### Scenario: Local conventions rendered as bullet list
- **WHEN** `serialize_aindex()` is called with `local_conventions=["Use UTC everywhere", "No bare prints"]`
- **THEN** the Local Conventions section SHALL render these as `- Use UTC everywhere` and `- No bare prints`

#### Scenario: Metadata footer serialized as HTML comment
- **WHEN** `serialize_aindex()` is called with a `StalenessMetadata` in the model
- **THEN** the output SHALL end with `<!-- lexibrary:meta` ... `-->` containing source, source_hash, generated, and generator fields

#### Scenario: Output ends with trailing newline
- **WHEN** `serialize_aindex()` is called with any valid input
- **THEN** the returned string SHALL end with `\n`

