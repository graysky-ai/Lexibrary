# linkgraph-pipeline-integration Specification

## Purpose
TBD - created by archiving change phase-10d-linkgraph-pipeline. Update Purpose after archive.
## Requirements
### Requirement: Link graph full build after update_project
After `update_project()` completes all design file generation and START_HERE.md regeneration, the system SHALL invoke `IndexBuilder.full_build()` to create or rebuild the link graph index at `.lexibrary/index.db`.

#### Scenario: Full build triggers on update_project
- **WHEN** `update_project()` finishes processing all source files and regenerating START_HERE.md
- **THEN** the system SHALL call `IndexBuilder.full_build()` with the project root and `.lexibrary/` path
- **AND** `UpdateStats.linkgraph_built` SHALL be set to `True` on success

#### Scenario: Full build runs after START_HERE.md
- **WHEN** `update_project()` runs the link graph build step
- **THEN** the build SHALL execute after START_HERE.md regeneration completes (or fails)
- **AND** the build SHALL have access to all freshly generated design files

### Requirement: Link graph incremental update after update_files
After `update_files()` completes processing its batch of changed files, the system SHALL invoke `IndexBuilder.incremental_update(changed_paths)` to update only the affected portions of the link graph index.

#### Scenario: Incremental update triggers on update_files
- **WHEN** `update_files()` finishes processing a batch of file paths
- **THEN** the system SHALL call `IndexBuilder.incremental_update()` with the list of processed file paths
- **AND** `UpdateStats.linkgraph_built` SHALL be set to `True` on success

#### Scenario: Deleted files forwarded to incremental update
- **WHEN** `update_files()` receives file paths that no longer exist on disk
- **THEN** those deleted paths SHALL be collected and included in the `incremental_update()` call
- **AND** the builder SHALL remove artifact rows and cascaded links for deleted files

#### Scenario: No files processed skips index update
- **WHEN** `update_files()` receives only files that are all skipped (deleted, binary, ignored)
- **THEN** `IndexBuilder.incremental_update()` SHALL still be called with any deleted paths if present
- **AND** if no deleted paths exist either, the index update MAY be skipped

### Requirement: Fail-safe index build wrapping
The link graph build step SHALL be wrapped in exception handling so that index build failures never prevent `update_project()` or `update_files()` from returning successfully.

#### Scenario: Index build failure does not block pipeline
- **WHEN** `IndexBuilder.full_build()` raises an exception during `update_project()`
- **THEN** the exception SHALL be caught and logged at ERROR level
- **AND** `UpdateStats.linkgraph_error` SHALL contain the error message
- **AND** `UpdateStats.linkgraph_built` SHALL remain `False`
- **AND** `update_project()` SHALL still return the `UpdateStats` with accurate design file statistics

#### Scenario: Incremental update failure does not block pipeline
- **WHEN** `IndexBuilder.incremental_update()` raises an exception during `update_files()`
- **THEN** the exception SHALL be caught and logged at ERROR level
- **AND** `UpdateStats.linkgraph_error` SHALL contain the error message
- **AND** `update_files()` SHALL still return the `UpdateStats` with accurate design file statistics

#### Scenario: SQLite corruption handled gracefully
- **WHEN** the index database is corrupt and the builder raises `sqlite3.DatabaseError`
- **THEN** the fail-safe wrapper SHALL catch the exception
- **AND** the error SHALL be logged with a message indicating potential database corruption

### Requirement: UpdateStats link graph fields
The `UpdateStats` dataclass SHALL include fields for reporting link graph build status.

#### Scenario: Successful build reported in stats
- **WHEN** the link graph build completes successfully
- **THEN** `UpdateStats.linkgraph_built` SHALL be `True`
- **AND** `UpdateStats.linkgraph_error` SHALL be `None`

#### Scenario: Failed build reported in stats
- **WHEN** the link graph build fails with an error
- **THEN** `UpdateStats.linkgraph_built` SHALL be `False`
- **AND** `UpdateStats.linkgraph_error` SHALL contain a string describing the error

#### Scenario: Default stats values
- **WHEN** an `UpdateStats` is created with default values
- **THEN** `linkgraph_built` SHALL default to `False`
- **AND** `linkgraph_error` SHALL default to `None`

### Requirement: IndexBuilder receives project context
The pipeline SHALL provide the `IndexBuilder` with the project root path and the `.lexibrary/` directory path, which are available from the pipeline's existing context.

#### Scenario: Builder receives project root
- **WHEN** the pipeline invokes `IndexBuilder`
- **THEN** it SHALL pass `project_root` (the same `Path` used throughout the pipeline)
- **AND** the builder SHALL use `project_root / LEXIBRARY_DIR` to locate `.lexibrary/`

### Requirement: index.db in .gitignore
The `lexictl init` scaffolder SHALL ensure that `index.db` is included in the project's `.gitignore` patterns so the link graph index is never committed to version control.

#### Scenario: Init includes index.db ignore pattern
- **WHEN** `lexictl init` creates or updates the project's `.gitignore`
- **THEN** the gitignore SHALL include a pattern matching `.lexibrary/index.db`

#### Scenario: Existing gitignore preserved
- **WHEN** `lexictl init` runs on a project with an existing `.gitignore`
- **THEN** the existing patterns SHALL be preserved
- **AND** the `index.db` pattern SHALL be appended if not already present

