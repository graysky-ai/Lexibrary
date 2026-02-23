# iandex-parser Specification

## Purpose
TBD - created by archiving change iandex-format. Update Purpose after archive.
## Requirements
### Requirement: Parse iandex file into IandexData
The system SHALL provide a `parse_iandex(path: Path) -> IandexData | None` function in `src/lexibrary/indexer/parser.py` that reads an existing `.aindex` file and returns a populated `IandexData` object.

#### Scenario: Parse well-formed iandex
- **WHEN** `parse_iandex()` is called with a path to a valid `.aindex` file
- **THEN** it SHALL return an `IandexData` with the correct `directory_name`, `summary`, `files`, and `subdirectories`

#### Scenario: Parsed file entries match content
- **WHEN** a `.aindex` file contains a files table with entries for `"cli.py"` (150 tokens) and `"config.py"` (200 tokens)
- **THEN** the returned `IandexData.files` SHALL contain two `FileEntry` objects with matching `name`, `tokens`, and `description` values

#### Scenario: Parsed directory entries match content
- **WHEN** a `.aindex` file contains a subdirectories table with an entry for `"config/"`
- **THEN** the returned `IandexData.subdirectories` SHALL contain a `DirEntry` with matching `name` and `description`

### Requirement: Return None for missing file
The parser SHALL return `None` when the specified path does not exist.

#### Scenario: Nonexistent file
- **WHEN** `parse_iandex()` is called with a path to a file that does not exist
- **THEN** it SHALL return `None`

### Requirement: Return None for malformed content
The parser SHALL return `None` when the file content does not start with a valid H1 header (`# ...`).

#### Scenario: Malformed file
- **WHEN** `parse_iandex()` is called with a path to a file containing arbitrary text without an H1 header
- **THEN** it SHALL return `None`

#### Scenario: Empty file
- **WHEN** `parse_iandex()` is called with a path to an empty file
- **THEN** it SHALL return `None`

### Requirement: Handle empty sections gracefully
The parser SHALL return empty lists for `files` and `subdirectories` when the corresponding sections contain `(none)` or no table rows.

#### Scenario: None marker in files section
- **WHEN** a `.aindex` file has `(none)` under the `## Files` heading
- **THEN** the returned `IandexData.files` SHALL be an empty list

#### Scenario: None marker in subdirectories section
- **WHEN** a `.aindex` file has `(none)` under the `## Subdirectories` heading
- **THEN** the returned `IandexData.subdirectories` SHALL be an empty list

### Requirement: No exceptions for invalid input
The parser SHALL NOT raise exceptions for missing files, unreadable files, or malformed content. It SHALL return `None` in all error cases.

#### Scenario: Unreadable file
- **WHEN** `parse_iandex()` is called with a path to a file that cannot be read (e.g., permission error, encoding error)
- **THEN** it SHALL return `None` without raising an exception

### Requirement: Parse H1 as directory name
The parser SHALL extract the directory name from the H1 header line (everything after `# `, stripped of whitespace).

#### Scenario: Directory name extraction
- **WHEN** a `.aindex` file starts with `# lexibrary/`
- **THEN** the returned `IandexData.directory_name` SHALL be `"lexibrary/"`

### Requirement: Parse summary from lines between H1 and first H2
The parser SHALL collect all non-empty lines between the H1 header and the first `##` header as the summary, joined with spaces.

#### Scenario: Multi-line summary
- **WHEN** a `.aindex` file has two non-empty lines between H1 and the first H2
- **THEN** the returned `IandexData.summary` SHALL be those lines joined with a single space

### Requirement: Cached file entries helper
The system SHALL provide a `get_cached_file_entries(iandex_path: Path) -> dict[str, FileEntry]` function that parses a `.aindex` file and returns file entries keyed by filename.

#### Scenario: Cached entries keyed by filename
- **WHEN** `get_cached_file_entries()` is called on a valid `.aindex` file containing entries for `"cli.py"` and `"config.py"`
- **THEN** it SHALL return a dict with keys `"cli.py"` and `"config.py"`, each mapping to the corresponding `FileEntry`

#### Scenario: Cached entries for missing file
- **WHEN** `get_cached_file_entries()` is called on a nonexistent path
- **THEN** it SHALL return an empty dict

### Requirement: Round-trip fidelity
The parser SHALL correctly parse any output produced by `generate_iandex()`, such that `parse_iandex(write_iandex(dir, generate_iandex(data)))` returns data equivalent to the original `IandexData`.

#### Scenario: Round-trip with files and subdirectories
- **WHEN** an `IandexData` with files and subdirectories is generated, written, and parsed
- **THEN** the parsed `IandexData` SHALL have identical `directory_name`, `summary`, `files`, and `subdirectories`

#### Scenario: Round-trip with empty sections
- **WHEN** an `IandexData` with no files and no subdirectories is generated, written, and parsed
- **THEN** the parsed `IandexData` SHALL have empty `files` and `subdirectories` lists

#### Scenario: Round-trip with Unicode content
- **WHEN** an `IandexData` with Unicode filenames and descriptions is generated, written, and parsed
- **THEN** all Unicode content SHALL be preserved exactly

