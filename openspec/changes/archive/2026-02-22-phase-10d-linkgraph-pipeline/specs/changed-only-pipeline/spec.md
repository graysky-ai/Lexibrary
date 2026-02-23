## MODIFIED Requirements

### Requirement: Batch file update function
The system SHALL provide an `update_files(file_paths, project_root, config, archivist, progress_callback)` function in `archivist/pipeline.py` that processes a specific list of source files and updates the link graph index incrementally.

#### Scenario: Process list of changed files
- **WHEN** `update_files()` is called with a list of file paths
- **THEN** each file SHALL be processed through `update_file()` sequentially
- **AND** accumulated `UpdateStats` SHALL be returned

#### Scenario: Skip deleted files in design file processing
- **WHEN** `update_files()` encounters a file path that does not exist (deleted in commit)
- **THEN** the file SHALL be skipped for design file processing

#### Scenario: Deleted files tracked for index cleanup
- **WHEN** `update_files()` encounters file paths that do not exist on disk
- **THEN** those deleted paths SHALL be collected
- **AND** forwarded to `IndexBuilder.incremental_update()` for artifact and link cleanup

#### Scenario: Skip binary files
- **WHEN** `update_files()` encounters a file with a binary extension
- **THEN** the file SHALL be skipped

#### Scenario: Skip ignored files
- **WHEN** `update_files()` encounters a file matching ignore patterns
- **THEN** the file SHALL be skipped

#### Scenario: Skip .lexibrary contents
- **WHEN** `update_files()` encounters a file inside the `.lexibrary/` directory
- **THEN** the file SHALL be skipped

#### Scenario: No START_HERE regeneration
- **WHEN** `update_files()` completes processing all files
- **THEN** `START_HERE.md` SHALL NOT be regenerated (that is a `update_project()` concern)

#### Scenario: Incremental index update after file processing
- **WHEN** `update_files()` finishes processing all files in the batch
- **THEN** `IndexBuilder.incremental_update()` SHALL be called with the processed and deleted file paths
- **AND** `UpdateStats.linkgraph_built` SHALL be `True` on success

#### Scenario: Index update failure does not block return
- **WHEN** `IndexBuilder.incremental_update()` raises an exception during `update_files()`
- **THEN** the exception SHALL be caught and logged at ERROR level
- **AND** `UpdateStats.linkgraph_error` SHALL contain the error message
- **AND** `update_files()` SHALL still return `UpdateStats` with accurate design file statistics

#### Scenario: Error handling per file
- **WHEN** `update_files()` encounters an unexpected error processing a file
- **THEN** the error SHALL be logged
- **AND** `files_failed` SHALL be incremented
- **AND** processing SHALL continue with the remaining files
