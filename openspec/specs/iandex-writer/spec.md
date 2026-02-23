# iandex-writer Specification

## Purpose
TBD - created by archiving change iandex-format. Update Purpose after archive.
## Requirements
### Requirement: Write iandex content to file
The system SHALL provide a `write_iandex(directory: Path, content: str, filename: str = ".aindex") -> Path` function in `src/lexibrary/indexer/writer.py` that writes the given content string to a file in the specified directory.

#### Scenario: Write creates file
- **WHEN** `write_iandex()` is called with a valid directory and content string
- **THEN** a file named `.aindex` SHALL exist in the directory after the call returns

#### Scenario: Written content matches input
- **WHEN** `write_iandex()` is called with a content string
- **THEN** reading the created file SHALL yield the exact same string

#### Scenario: Return value is file path
- **WHEN** `write_iandex()` is called
- **THEN** it SHALL return the `Path` to the written file

### Requirement: Atomic write operation
The writer SHALL use a temp-file-then-rename strategy to ensure atomicity. It SHALL write to a temporary file in the same directory, then use `os.replace()` to atomically move it to the target path.

#### Scenario: No partial files on interruption
- **WHEN** the write operation fails (e.g., exception during `f.write()`)
- **THEN** the target file SHALL NOT contain partial content, and any temporary files SHALL be cleaned up

#### Scenario: Temp file in same directory
- **WHEN** `write_iandex()` creates a temporary file
- **THEN** the temporary file SHALL be created in the same directory as the target to guarantee same-filesystem atomic rename

### Requirement: Overwrite existing file
The writer SHALL cleanly overwrite an existing `.aindex` file when called on a directory that already has one.

#### Scenario: Second write overwrites first
- **WHEN** `write_iandex()` is called twice on the same directory with different content
- **THEN** the file SHALL contain only the content from the second call

### Requirement: UTF-8 encoding
The writer SHALL write files using UTF-8 encoding.

#### Scenario: Unicode content preserved
- **WHEN** `write_iandex()` is called with content containing Unicode characters (e.g., `"ñ"`, `"日本語"`)
- **THEN** reading the file back with UTF-8 encoding SHALL yield the original content

### Requirement: Custom filename support
The writer SHALL accept an optional `filename` parameter to write to a name other than `.aindex`.

#### Scenario: Custom filename
- **WHEN** `write_iandex()` is called with `filename=".aindex.bak"`
- **THEN** the file SHALL be written as `.aindex.bak` in the target directory

