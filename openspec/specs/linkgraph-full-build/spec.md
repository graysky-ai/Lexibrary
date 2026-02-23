# linkgraph-full-build Specification

## Purpose
TBD - created by archiving change phase-10b-linkgraph-builder. Update Purpose after archive.
## Requirements
### Requirement: IndexBuilder class instantiation
The `IndexBuilder` class SHALL accept a `sqlite3.Connection` and a `project_root: Path` as constructor arguments. The connection MUST have pragmas already set via `set_pragmas()`. The builder SHALL NOT manage the database file lifecycle.

#### Scenario: Successful instantiation
- **WHEN** an `IndexBuilder` is created with a valid connection and project root
- **THEN** the builder stores both as instance attributes and is ready for `full_build()` or `incremental_update()` calls

#### Scenario: Connection without pragmas
- **WHEN** an `IndexBuilder` is created with a connection that has not had `set_pragmas()` called
- **THEN** the builder SHALL call `set_pragmas()` on the connection during instantiation as a safety measure

### Requirement: Full build cleans stale build log entries
The `full_build()` method SHALL delete all `build_log` rows where `build_started` is older than 30 days before starting the main build transaction.

#### Scenario: Build log with entries older than 30 days
- **WHEN** `full_build()` is called and the `build_log` contains entries from 45 days ago and 10 days ago
- **THEN** the 45-day-old entries are deleted and the 10-day-old entries are preserved

#### Scenario: Empty build log
- **WHEN** `full_build()` is called and the `build_log` is empty
- **THEN** the cleanup step completes without error

### Requirement: Full build ensures schema with version check
The `full_build()` method SHALL call `ensure_schema()` on the connection. If the schema version does not match `SCHEMA_VERSION`, the schema MUST be dropped and recreated.

#### Scenario: Schema version matches
- **WHEN** `full_build()` is called and the existing schema version matches `SCHEMA_VERSION`
- **THEN** the schema is kept as-is and the build proceeds

#### Scenario: Schema version mismatch
- **WHEN** `full_build()` is called and the stored schema version differs from `SCHEMA_VERSION`
- **THEN** all tables are dropped and recreated before the build proceeds

#### Scenario: No existing schema
- **WHEN** `full_build()` is called on a fresh database with no tables
- **THEN** the schema is created and the build proceeds

### Requirement: Full build clears all existing rows
After ensuring the schema, `full_build()` SHALL delete all rows from all data tables (artifacts, links, tags, aliases, conventions, build_log recent entries are preserved, artifacts_fts) before inserting new data.

#### Scenario: Database with existing data from a prior build
- **WHEN** `full_build()` is called on a database containing artifacts and links from a previous build
- **THEN** all existing artifact, link, tag, alias, convention, and FTS rows are deleted before new data is inserted

### Requirement: Full build indexes design files with source artifacts
For each design file discovered in `.lexibrary/src/`, the builder SHALL:
1. Insert a `kind='source'` artifact with the source file's project-relative path, the title from the design file frontmatter description, the SHA-256 hash of the source file, and the file's creation timestamp
2. Insert a `kind='design'` artifact for the design file itself
3. Insert a `design_source` link from the design artifact to the source artifact

#### Scenario: Design file for an existing source file
- **WHEN** `full_build()` processes a design file at `.lexibrary/src/auth/login.py.md` for source file `src/auth/login.py`
- **THEN** a `kind='source'` artifact is inserted with path `src/auth/login.py`, a `kind='design'` artifact is inserted with path `.lexibrary/src/auth/login.py.md`, and a `design_source` link connects design to source

#### Scenario: Design file for a deleted source file
- **WHEN** `full_build()` processes a design file whose corresponding source file no longer exists on disk
- **THEN** the source artifact is still inserted (with null hash) and the design artifact and link are created, preserving the historical record

### Requirement: Full build extracts AST import links
For each source file with a design file, the builder SHALL call `extract_dependencies()` to find project-internal imports and insert `ast_import` links from the source artifact to each dependency's source artifact.

#### Scenario: Source file with project-internal imports
- **WHEN** `full_build()` processes `src/auth/login.py` which imports `src/config/schema.py` and `src/utils/hashing.py`
- **THEN** `ast_import` links are created from the `src/auth/login.py` artifact to both `src/config/schema.py` and `src/utils/hashing.py` artifacts

#### Scenario: Source file with only external imports
- **WHEN** `full_build()` processes a source file that only imports third-party packages (e.g., `pydantic`, `typer`)
- **THEN** no `ast_import` links are created and no artifact rows are created for the external packages

#### Scenario: Import target has no design file
- **WHEN** a source file imports another project file that exists on disk but has no design file
- **THEN** a stub `kind='source'` artifact is created for the import target so the `ast_import` link can reference it

### Requirement: Full build indexes design file wikilinks
For each design file, the builder SHALL extract wikilinks from `DesignFile.wikilinks` and insert `wikilink` links from the design artifact to the referenced concept artifact.

#### Scenario: Design file with wikilinks to existing concepts
- **WHEN** a design file has `wikilinks: ["Authentication", "MoneyHandling"]`
- **THEN** `wikilink` links are created from the design artifact to the `Authentication` and `MoneyHandling` concept artifacts

#### Scenario: Design file with wikilink to non-existent concept
- **WHEN** a design file references `[[NonExistentConcept]]` but no such concept file exists
- **THEN** a stub `kind='concept'` artifact is created with a synthetic path and the wikilink link is still inserted

### Requirement: Full build indexes design file Stack references
For each design file, the builder SHALL extract Stack post references from `DesignFile.stack_refs` and insert `design_stack_ref` links from the design artifact to the referenced Stack artifact.

#### Scenario: Design file with Stack references
- **WHEN** a design file has `stack_refs: ["ST-001", "ST-003"]`
- **THEN** `design_stack_ref` links are created from the design artifact to the `ST-001` and `ST-003` Stack artifacts

### Requirement: Full build indexes design file tags
For each design file, the builder SHALL insert rows into the `tags` table associating the design artifact with each tag from `DesignFile.tags`.

#### Scenario: Design file with tags
- **WHEN** a design file has `tags: ["auth", "security", "login"]`
- **THEN** three rows are inserted into the `tags` table linking the design artifact to each tag

### Requirement: Full build populates FTS for design files
For each design file, the builder SHALL insert an FTS row into `artifacts_fts` with the rowid matching the design artifact's ID. The title SHALL be the frontmatter description. The body SHALL be the concatenation of summary and interface_contract.

#### Scenario: Design file FTS insertion
- **WHEN** `full_build()` processes a design file with summary "Handles user login" and interface_contract "def login(username, password)"
- **THEN** an FTS row is inserted with title from frontmatter and body "Handles user login\ndef login(username, password)"

### Requirement: Full build indexes concept files
For each concept file in `.lexibrary/concepts/`, the builder SHALL:
1. Insert a `kind='concept'` artifact with the concept's path, title, status from frontmatter
2. Insert aliases from `ConceptFileFrontmatter.aliases` into the `aliases` table
3. Extract `[[wikilinks]]` from the concept body and insert `wikilink` links to other concept artifacts
4. Insert `concept_file_ref` links from `ConceptFile.linked_files`
5. Insert tags from `ConceptFileFrontmatter.tags`
6. Insert an FTS row with body = summary + body

#### Scenario: Concept file with aliases, wikilinks, and linked files
- **WHEN** `full_build()` processes `Authentication.md` with aliases `["auth", "authn"]`, body containing `[[Authorization]]`, and linked_files `["src/auth/login.py"]`
- **THEN** a concept artifact is inserted, two alias rows are inserted, a `wikilink` link to `Authorization` is created, a `concept_file_ref` link to `src/auth/login.py` is created, and tags and FTS content are populated

### Requirement: Alias uniqueness with first-writer-wins
When inserting aliases, if an alias (case-insensitive) is already claimed by another concept, the builder SHALL skip the duplicate alias and log a warning message identifying both concepts.

#### Scenario: Two concepts claim the same alias
- **WHEN** concept `Authentication` defines alias `auth` and concept `Authorization` also defines alias `auth`
- **THEN** the first concept processed (by sorted path order) gets the alias, the second is skipped, and a warning is logged

### Requirement: Full build indexes Stack posts
For each Stack post in `.lexibrary/stack/`, the builder SHALL:
1. Insert a `kind='stack'` artifact with the post's path, title, status from frontmatter
2. Insert `stack_file_ref` links from `StackPostFrontmatter.refs.files`
3. Insert `stack_concept_ref` links from `StackPostFrontmatter.refs.concepts`
4. Insert tags from `StackPostFrontmatter.tags`
5. Insert an FTS row with body = problem + answer bodies

#### Scenario: Stack post with file and concept references
- **WHEN** `full_build()` processes `ST-001-timezone-naive-datetimes.md` with `refs.files: ["src/utils/dates.py"]` and `refs.concepts: ["Timezones"]`
- **THEN** a stack artifact is inserted, a `stack_file_ref` link to `src/utils/dates.py` is created, a `stack_concept_ref` link to `Timezones` is created, and tags and FTS are populated

### Requirement: Full build indexes local conventions from .aindex files
For each `.aindex` file, the builder SHALL process each entry in `AIndexFile.local_conventions`:
1. Insert a `kind='convention'` artifact with synthetic path `{directory_path}::convention::{ordinal}` and title = first 120 characters of the convention text
2. Insert a row in the `conventions` table with `directory_path`, `ordinal`, and `body`
3. Extract `[[wikilinks]]` from the convention text and insert `convention_concept_ref` links
4. Insert an FTS row with body = full convention text

#### Scenario: .aindex file with two local conventions
- **WHEN** `full_build()` processes `.lexibrary/src/auth/.aindex` with two local conventions
- **THEN** two convention artifacts are inserted with paths `src/auth::convention::0` and `src/auth::convention::1`, two convention rows are created, any wikilinks are linked, and FTS rows are populated

#### Scenario: Convention text contains wikilinks
- **WHEN** a local convention contains `"All endpoints must use [[Authentication]] middleware"`
- **THEN** a `convention_concept_ref` link is created from the convention artifact to the `Authentication` concept artifact

### Requirement: Full build updates meta table
After all artifacts and links are inserted, `full_build()` SHALL update the `meta` table with:
- `built_at`: current ISO 8601 timestamp
- `builder`: identifier string (e.g., `"lexibrary-v2"`)
- `artifact_count`: total number of rows in `artifacts`
- `link_count`: total number of rows in `links`

#### Scenario: Successful full build with 100 artifacts and 250 links
- **WHEN** `full_build()` completes successfully
- **THEN** the `meta` table contains `artifact_count=100`, `link_count=250`, a current `built_at` timestamp, and the builder identifier

### Requirement: Full build logs to build_log
For each artifact processed during `full_build()`, the builder SHALL insert a row into `build_log` with `build_type='full'`, the artifact path and kind, action `'created'`, duration in milliseconds, and any error message.

#### Scenario: Successful artifact processing
- **WHEN** a design file is processed without errors during full build
- **THEN** a `build_log` row is inserted with `action='created'`, `build_type='full'`, and the elapsed duration

#### Scenario: Failed artifact processing
- **WHEN** a design file fails to parse during full build
- **THEN** a `build_log` row is inserted with `action='failed'` and the error message

### Requirement: Full build returns a BuildResult
`full_build()` SHALL return a `BuildResult` dataclass containing: `artifact_count`, `link_count`, `duration_ms`, `errors` (list of error strings), and `build_type='full'`.

#### Scenario: Successful full build
- **WHEN** `full_build()` completes with 100 artifacts and 250 links in 1200ms
- **THEN** the returned `BuildResult` has `artifact_count=100`, `link_count=250`, `duration_ms=1200`, `errors=[]`, `build_type='full'`

### Requirement: Wikilink extraction from text
The builder SHALL provide a utility function to extract `[[wikilink]]` patterns from arbitrary text (used for concept body scanning and convention text scanning). The function SHALL return a deduplicated list of wikilink target names.

#### Scenario: Text with multiple wikilinks
- **WHEN** the text `"Uses [[Authentication]] and [[Authorization]] for [[Authentication]] checks"` is scanned
- **THEN** the result is `["Authentication", "Authorization"]` (deduplicated)

#### Scenario: Text with no wikilinks
- **WHEN** plain text with no `[[...]]` patterns is scanned
- **THEN** an empty list is returned

### Requirement: build_index() public API function
The module SHALL expose a `build_index(project_root: Path, changed_paths: list[Path] | None = None) -> BuildResult` function. When `changed_paths` is None, it performs a full build. When provided, it performs an incremental update.

#### Scenario: Full build via public API
- **WHEN** `build_index(project_root)` is called with no `changed_paths`
- **THEN** a full build is performed and a `BuildResult` is returned

#### Scenario: Incremental update via public API
- **WHEN** `build_index(project_root, changed_paths=[Path("src/auth/login.py")])` is called
- **THEN** an incremental update is performed for the specified paths and a `BuildResult` is returned

### Requirement: open_index() public API function
The module SHALL expose an `open_index(project_root: Path) -> sqlite3.Connection | None` function that opens `.lexibrary/index.db` with pragmas set, or returns `None` if the file does not exist or is corrupt.

#### Scenario: Index database exists
- **WHEN** `open_index()` is called and `.lexibrary/index.db` exists with a valid schema
- **THEN** a `sqlite3.Connection` with pragmas set is returned

#### Scenario: Index database does not exist
- **WHEN** `open_index()` is called and `.lexibrary/index.db` does not exist
- **THEN** `None` is returned

#### Scenario: Index database is corrupt
- **WHEN** `open_index()` is called and `.lexibrary/index.db` exists but is corrupt
- **THEN** `None` is returned after catching `sqlite3.DatabaseError`

