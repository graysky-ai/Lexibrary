## MODIFIED Requirements

### Requirement: update_project function
The system SHALL provide `async update_project(project_root, config, archivist, progress_callback?) -> UpdateStats` that updates all design files for the project.

The pipeline SHALL:
1. Create IgnoreMatcher (includes `.lexignore`)
2. Discover all source files within `scope_root`
3. Filter: skip `.lexibrary/` contents, binary files, files outside scope
4. Build concept name list from `.lexibrary/concepts/` if the directory exists
5. For each file: call `update_file()` with `available_concepts` (sequential)
6. After all files: call `generate_start_here()`
7. Build/rebuild the link graph index via `IndexBuilder.full_build()`
8. Return UpdateStats

#### Scenario: Discovers files within scope
- **WHEN** `update_project()` runs with `scope_root` set to `"src/"`
- **THEN** only files under `src/` SHALL be processed

#### Scenario: Binary files skipped
- **WHEN** `update_project()` encounters a binary file (matched by binary_extensions)
- **THEN** the file SHALL be skipped

#### Scenario: .lexibrary contents skipped
- **WHEN** `update_project()` discovers files
- **THEN** files under `.lexibrary/` SHALL NOT be processed

#### Scenario: Stats correctly tracked
- **WHEN** `update_project()` completes
- **THEN** `UpdateStats` SHALL accurately reflect counts for scanned, unchanged, agent_updated, updated, created, failed, aindex_refreshed, token_budget_warnings, linkgraph_built, and linkgraph_error

#### Scenario: Concept names loaded for pipeline
- **WHEN** `update_project()` runs and `.lexibrary/concepts/` contains 3 concept files
- **THEN** all `update_file()` calls SHALL receive `available_concepts` with 3 concept names

#### Scenario: No concepts directory
- **WHEN** `update_project()` runs and `.lexibrary/concepts/` doesn't exist
- **THEN** `update_file()` calls SHALL receive `available_concepts=None`

#### Scenario: Link graph built after design files and START_HERE
- **WHEN** `update_project()` completes
- **THEN** the link graph index SHALL be built after all design files are generated and START_HERE.md is regenerated
- **AND** `UpdateStats.linkgraph_built` SHALL be `True` on success

#### Scenario: Link graph failure does not affect design file stats
- **WHEN** `update_project()` completes design file generation successfully but the link graph build fails
- **THEN** design file statistics (files_scanned, files_updated, etc.) SHALL still be accurate
- **AND** `UpdateStats.linkgraph_error` SHALL contain the error message

### Requirement: UpdateStats tracking
The system SHALL provide an `UpdateStats` dataclass with fields: `files_scanned`, `files_unchanged`, `files_agent_updated`, `files_updated`, `files_created`, `files_failed`, `aindex_refreshed`, `token_budget_warnings` (all int, default 0), `start_here_failed` (bool, default False), `linkgraph_built` (bool, default False), `linkgraph_error` (str | None, default None).

#### Scenario: Stats accumulate correctly
- **WHEN** multiple files are processed with different change levels
- **THEN** each counter SHALL increment for its respective change level

#### Scenario: Link graph stats default values
- **WHEN** an `UpdateStats` instance is created with no arguments
- **THEN** `linkgraph_built` SHALL be `False`
- **AND** `linkgraph_error` SHALL be `None`
