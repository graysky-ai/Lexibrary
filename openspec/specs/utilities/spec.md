# utilities Specification

## Purpose
TBD - created by archiving change phase-1-foundation. Update Purpose after archive.
## Requirements
### Requirement: File hashing
The system SHALL compute SHA-256 hashes of file contents for integrity checking. Hashing SHALL read files in chunks to handle large files efficiently. The system SHALL additionally provide a `hash_string(text: str) -> str` function that computes the SHA-256 hex digest of a UTF-8 encoded string.

#### Scenario: Hash is computed for small file
- **WHEN** calling `hash_file(path)` on a small text file with known content
- **THEN** it returns a 64-character hexadecimal string (SHA-256 digest)

#### Scenario: Same file content produces same hash
- **WHEN** calling `hash_file()` twice on the same file
- **THEN** both calls return identical hash strings

#### Scenario: Different file content produces different hash
- **WHEN** calling `hash_file()` on two files with different content
- **THEN** the hashes are different

#### Scenario: Large files are hashed in chunks
- **WHEN** calling `hash_file()` on a file larger than the chunk size (8192 bytes by default)
- **THEN** it reads and processes the file in chunks, returning the correct SHA-256 hash

#### Scenario: String hashing produces valid SHA-256
- **WHEN** calling `hash_string("hello world")`
- **THEN** it returns a 64-character hexadecimal SHA-256 digest of the UTF-8 encoded string

#### Scenario: Same string produces same hash
- **WHEN** calling `hash_string()` twice with the same text
- **THEN** both calls return identical hash strings

#### Scenario: Empty string produces valid hash
- **WHEN** calling `hash_string("")`
- **THEN** it returns the SHA-256 hash of an empty byte string (a valid 64-char hex digest)

### Requirement: Logging setup
The system SHALL provide a function to configure logging with Rich handler for console output and optional file handler for persistent logs.

#### Scenario: Logging is configured with defaults
- **WHEN** calling `setup_logging()` with no arguments
- **THEN** logging is configured at INFO level with RichHandler enabled and no file logging

#### Scenario: Verbose mode enables DEBUG logging
- **WHEN** calling `setup_logging(verbose=True)`
- **THEN** logging level is set to DEBUG

#### Scenario: File logging is enabled
- **WHEN** calling `setup_logging(log_file=".lexibrary.log")`
- **THEN** a FileHandler is added that writes to the specified file

#### Scenario: Log messages are formatted correctly
- **WHEN** emitting a log message after setup
- **THEN** it includes the message content with Rich formatting (no redundant timestamps)

### Requirement: Project root discovery
The system SHALL find the project root by walking upward from a start directory, looking for `.git` directory or `lexibrary.toml` file. Falls back to current working directory if nothing is found.

#### Scenario: Project root with .git is found
- **WHEN** calling `find_project_root()` from anywhere in a Git repository
- **THEN** it returns the directory containing the `.git` folder

#### Scenario: Project root with lexibrary.toml is found
- **WHEN** calling `find_project_root()` from anywhere in a project with `lexibrary.toml` at root
- **THEN** it returns the directory containing `lexibrary.toml`

#### Scenario: Closest root marker is returned
- **WHEN** a project has both `.git` and `lexibrary.toml` at the root, and is inside a Git repository
- **THEN** the closest root directory to the start point is returned

#### Scenario: No root markers found returns current directory
- **WHEN** calling `find_project_root()` from a directory with no `.git` or `lexibrary.toml` anywhere in parents
- **THEN** it returns the current working directory

#### Scenario: Root is found from a subdirectory
- **WHEN** calling `find_project_root(start=Path("/some/nested/subdirectory"))`
- **THEN** it walks upward and returns the first directory containing `.git` or `lexibrary.toml`

### Requirement: IWH path computation
The system SHALL provide `iwh_path(project_root: Path, source_directory: Path) -> Path` in `src/lexibrary/utils/paths.py` that computes the `.iwh` file path in the `.lexibrary/` mirror tree.

#### Scenario: Subdirectory IWH path
- **WHEN** calling `iwh_path(project_root, project_root / "src" / "auth")`
- **THEN** it SHALL return `project_root / ".lexibrary" / "src" / "auth" / ".iwh"`

#### Scenario: Project root IWH path
- **WHEN** calling `iwh_path(project_root, project_root)`
- **THEN** it SHALL return `project_root / ".lexibrary" / ".iwh"`

#### Scenario: Nested directory IWH path
- **WHEN** calling `iwh_path(project_root, project_root / "src" / "auth" / "middleware")`
- **THEN** it SHALL return `project_root / ".lexibrary" / "src" / "auth" / "middleware" / ".iwh"`

