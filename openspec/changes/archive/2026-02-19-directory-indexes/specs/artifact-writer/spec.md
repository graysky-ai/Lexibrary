## ADDED Requirements

### Requirement: Atomic artifact file write
The system SHALL provide a `write_artifact(target: Path, content: str) -> Path` function in `src/lexibrary/artifacts/writer.py` that writes a string to a file atomically.

The function SHALL:
- Create all parent directories if they do not exist (`parents=True`)
- Write content to a temporary file alongside the target (same directory)
- Rename the temporary file to the target path (atomic on POSIX — same filesystem)
- Return the target path
- Write content as UTF-8

#### Scenario: Write creates file with correct content
- **WHEN** `write_artifact()` is called with a path and a content string
- **THEN** the file at the target path SHALL exist and contain exactly the provided content

#### Scenario: Write creates parent directories
- **WHEN** `write_artifact()` is called with a path whose parent directories do not yet exist
- **THEN** the parent directories SHALL be created and the file SHALL be written successfully

#### Scenario: Write overwrites existing file
- **WHEN** `write_artifact()` is called twice with the same path and different content
- **THEN** the file SHALL contain the second content (old content replaced)

#### Scenario: Write is atomic
- **WHEN** `write_artifact()` completes normally
- **THEN** no `.tmp` file SHALL remain alongside the target — only the final target file exists

#### Scenario: Write returns target path
- **WHEN** `write_artifact()` is called with a target path
- **THEN** the returned value SHALL be equal to the target path
