# linkgraph-incremental-update Specification

## Purpose
TBD - created by archiving change phase-10b-linkgraph-builder. Update Purpose after archive.
## Requirements
### Requirement: Incremental update accepts changed file paths
The `incremental_update(changed_paths: list[Path])` method SHALL accept a list of file paths that have been modified or deleted since the last build.

#### Scenario: Single changed source file
- **WHEN** `incremental_update([Path("src/auth/login.py")])` is called
- **THEN** only the artifacts related to `src/auth/login.py` are reprocessed

#### Scenario: Multiple changed files of mixed types
- **WHEN** `incremental_update()` is called with a list containing a source file, a concept file, and a Stack post path
- **THEN** each file is reprocessed according to its artifact type

### Requirement: Incremental update cleans stale build log entries
Before processing changed files, `incremental_update()` SHALL delete all `build_log` rows where `build_started` is older than 30 days, identical to the full build cleanup.

#### Scenario: Stale build log entries exist
- **WHEN** `incremental_update()` is called and the `build_log` contains entries from 35 days ago
- **THEN** the stale entries are deleted before processing begins

### Requirement: Incremental update deletes outbound data for changed files
For each changed file that still exists on disk, the builder SHALL delete:
1. All outbound links (where `source_id` matches the file's artifact)
2. All tags for the artifact
3. All aliases for the artifact (if it is a concept)
4. The FTS row for the artifact

The artifact row itself SHALL be preserved (updated in place).

#### Scenario: Changed source file with existing links and tags
- **WHEN** `incremental_update()` processes a changed source file that had 3 `ast_import` links and 2 tags
- **THEN** all 3 links and 2 tags are deleted, and the artifact row's `last_hash` is updated

#### Scenario: Changed concept file with aliases
- **WHEN** `incremental_update()` processes a changed concept file that had 2 aliases
- **THEN** all aliases, links, tags, and the FTS row for the concept are deleted before re-extraction

### Requirement: Incremental update re-extracts and reinserts from current content
After deleting outbound data, the builder SHALL re-read the file from disk, re-parse it, and reinsert all links, tags, aliases, and FTS content as if building from scratch for that single artifact.

#### Scenario: Source file gained a new import
- **WHEN** `src/auth/login.py` is updated to add `from src.utils.crypto import encrypt` and `incremental_update()` processes it
- **THEN** the new `ast_import` link to `src/utils/crypto.py` is inserted alongside any existing imports

#### Scenario: Concept file alias changed
- **WHEN** concept `Authentication` changes its aliases from `["auth"]` to `["auth", "authn"]`
- **THEN** after incremental update, the aliases table contains both `auth` and `authn` for the concept

#### Scenario: Design file wikilinks updated
- **WHEN** a design file previously referenced `[[Authentication]]` and now also references `[[Authorization]]`
- **THEN** after incremental update, both wikilink links exist from the design artifact

### Requirement: Incremental update handles deleted files
If a file in `changed_paths` no longer exists on disk, the builder SHALL delete the corresponding artifact row. SQLite `ON DELETE CASCADE` will automatically clean up all related links, tags, aliases, conventions, and the FTS row.

#### Scenario: Source file deleted
- **WHEN** `incremental_update([Path("src/old_module.py")])` is called and `src/old_module.py` no longer exists
- **THEN** the `kind='source'` artifact for `src/old_module.py` is deleted, and all its links, tags, and FTS row are removed via CASCADE

#### Scenario: Design file and source file both deleted
- **WHEN** both a source file and its corresponding design file are in `changed_paths` and neither exists on disk
- **THEN** both artifact rows are deleted with CASCADE cleanup

#### Scenario: Concept file deleted
- **WHEN** a concept file is deleted and appears in `changed_paths`
- **THEN** the concept artifact, its aliases, links, tags, and FTS row are all removed

### Requirement: Incremental update handles design file changes
When a design file path appears in `changed_paths`, the builder SHALL:
1. Re-parse the design file
2. Update the design artifact's `title` and `last_hash`
3. Delete and reinsert the design artifact's outbound links (wikilinks, stack_refs, design_source)
4. Delete and reinsert tags and FTS content
5. Re-extract AST imports for the associated source file and update `ast_import` links

#### Scenario: Design file content changed
- **WHEN** a design file's summary and wikilinks are modified
- **THEN** the design artifact's title is updated, old wikilink links are deleted, new ones are inserted, and the FTS row is updated

### Requirement: Incremental update handles .aindex convention changes
When an `.aindex` file path appears in `changed_paths`, the builder SHALL:
1. Delete all convention artifacts whose `directory_path` matches the `.aindex` file's directory
2. Re-parse the `.aindex` file and reinsert convention artifacts, convention rows, links, and FTS rows

#### Scenario: .aindex file gains a new local convention
- **WHEN** `.lexibrary/src/auth/.aindex` is updated to add a third local convention
- **THEN** all existing convention artifacts for `src/auth` are deleted and three new ones are inserted

#### Scenario: .aindex file removed
- **WHEN** an `.aindex` file is deleted and appears in `changed_paths`
- **THEN** all convention artifacts for that directory are deleted with CASCADE cleanup

### Requirement: Incremental update updates meta counts
After processing all changed files, `incremental_update()` SHALL update the `meta` table with current `artifact_count`, `link_count`, and `built_at` values by querying the actual table counts.

#### Scenario: After incremental update of 3 files
- **WHEN** `incremental_update()` completes processing 3 changed files
- **THEN** the `meta` table reflects the current total counts of artifacts and links in the database

### Requirement: Incremental update logs to build_log
For each changed file processed, the builder SHALL insert a `build_log` row with `build_type='incremental'`, the artifact path and kind, the appropriate action (`'updated'` for modified files, `'deleted'` for removed files, `'failed'` for errors), duration, and any error message.

#### Scenario: Successfully updated file
- **WHEN** a changed file is reprocessed without errors
- **THEN** a `build_log` row with `action='updated'` and `build_type='incremental'` is inserted

#### Scenario: Deleted file
- **WHEN** a deleted file is processed
- **THEN** a `build_log` row with `action='deleted'` and `build_type='incremental'` is inserted

#### Scenario: File processing fails
- **WHEN** a changed file fails to parse
- **THEN** a `build_log` row with `action='failed'` and the error message is inserted, and processing continues with the next file

### Requirement: Incremental update returns a BuildResult
`incremental_update()` SHALL return a `BuildResult` dataclass with `artifact_count`, `link_count`, `duration_ms`, `errors`, and `build_type='incremental'`.

#### Scenario: Successful incremental update
- **WHEN** `incremental_update()` processes 3 files in 150ms with no errors
- **THEN** the returned `BuildResult` has the current total counts, `duration_ms=150`, `errors=[]`, `build_type='incremental'`

### Requirement: Incremental update is resilient to per-file errors
If processing one file in `changed_paths` raises an exception, the builder SHALL log the error, record it in `build_log`, and continue processing the remaining files. The error SHALL be included in the returned `BuildResult.errors`.

#### Scenario: One file fails, others succeed
- **WHEN** `incremental_update()` is called with 3 files and the second file raises a parse error
- **THEN** the first and third files are processed normally, the second file's error is logged and recorded, and the `BuildResult.errors` list contains the error message

### Requirement: Incremental update maps changed paths to artifact types
The builder SHALL determine the artifact type from the file path:
- Paths under `.lexibrary/concepts/` are concept files
- Paths under `.lexibrary/stack/` are Stack posts
- Paths ending in `.aindex` under `.lexibrary/` are aindex files
- Paths ending in `.md` under `.lexibrary/src/` are design files
- All other paths are treated as source files

#### Scenario: Mixed changed paths
- **WHEN** `incremental_update()` receives paths `["src/auth/login.py", ".lexibrary/concepts/Auth.md", ".lexibrary/stack/ST-001.md"]`
- **THEN** the first is processed as a source file, the second as a concept, and the third as a Stack post

#### Scenario: Source file change triggers design file re-read
- **WHEN** a source file path is in `changed_paths` and a design file exists for it
- **THEN** the builder re-reads the design file to extract updated wikilinks, tags, and stack refs, and re-extracts AST imports from the source file

