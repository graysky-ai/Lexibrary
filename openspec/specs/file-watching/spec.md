# file-watching Specification

## Purpose
TBD - created by archiving change daemon. Update Purpose after archive.
## Requirements
### Requirement: File system event handling
The system SHALL provide a `LexibraryEventHandler` that extends watchdog's `FileSystemEventHandler` and receives all file system events within the watched project directory tree.

#### Scenario: Handler receives file creation event
- **WHEN** a new file is created in the watched directory tree
- **THEN** the handler processes the event and notifies the debouncer with the parent directory of the created file

#### Scenario: Handler receives file modification event
- **WHEN** an existing file is modified in the watched directory tree
- **THEN** the handler processes the event and notifies the debouncer with the parent directory of the modified file

#### Scenario: Handler receives file deletion event
- **WHEN** a file is deleted from the watched directory tree
- **THEN** the handler processes the event and notifies the debouncer with the parent directory of the deleted file

### Requirement: Directory event filtering
The system SHALL ignore all directory-level events (directory created, modified, deleted, moved) since only file changes are relevant for re-indexing.

#### Scenario: Directory creation is ignored
- **WHEN** a new directory is created in the watched tree
- **THEN** the handler does NOT notify the debouncer

#### Scenario: Directory deletion is ignored
- **WHEN** a directory is deleted from the watched tree
- **THEN** the handler does NOT notify the debouncer

### Requirement: Index file filtering
The system SHALL ignore changes to files whose name starts with `.aindex` to prevent infinite re-indexing loops where daemon-generated output triggers further re-indexing.

#### Scenario: iandex file change is ignored
- **WHEN** a `.aindex` file is created or modified in the watched tree
- **THEN** the handler does NOT notify the debouncer

#### Scenario: iandex variant file change is ignored
- **WHEN** a file named `.aindex.bak` or `.aindex_tmp` is modified
- **THEN** the handler does NOT notify the debouncer

### Requirement: Internal file filtering
The system SHALL ignore changes to Lexibrary's own operational files: the cache file (`.lexibrary_cache.json`), log file (`.lexibrary.log`), and PID file (`.lexibrary.pid`).

#### Scenario: Cache file change is ignored
- **WHEN** the `.lexibrary_cache.json` file is modified
- **THEN** the handler does NOT notify the debouncer

#### Scenario: Log file change is ignored
- **WHEN** the `.lexibrary.log` file is modified
- **THEN** the handler does NOT notify the debouncer

#### Scenario: PID file change is ignored
- **WHEN** the `.lexibrary.pid` file is created or deleted
- **THEN** the handler does NOT notify the debouncer

### Requirement: Ignore pattern filtering
The system SHALL check each file event against the project's `IgnoreMatcher` (gitignore + config patterns) and skip files that match ignore rules.

#### Scenario: Gitignored file change is ignored
- **WHEN** a file matching a `.gitignore` pattern is modified
- **THEN** the handler does NOT notify the debouncer

#### Scenario: Config-ignored file change is ignored
- **WHEN** a file matching a pattern in `lexibrary.toml` ignore list is modified
- **THEN** the handler does NOT notify the debouncer

#### Scenario: Non-ignored file change triggers notification
- **WHEN** a file not matching any ignore pattern is modified
- **THEN** the handler notifies the debouncer with the file's parent directory

