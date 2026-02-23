## MODIFIED Requirements

### Requirement: update_file function
The system SHALL provide `async update_file(source_path, project_root, config, archivist, available_concepts: list[str] | None = None) -> ChangeLevel` in `src/lexibrary/archivist/pipeline.py` that generates or updates the design file for a single source file.

The pipeline for a single file SHALL:
1. Check `scope_root` — skip if file is outside scope
2. Compute content and interface hashes
3. Run change detection (`check_change`)
4. If UNCHANGED → return early
5. If AGENT_UPDATED → refresh footer hashes only (no LLM call)
6. For NEW_FILE / CONTENT_ONLY / CONTENT_CHANGED / INTERFACE_CHANGED → parse interface, read source, call Archivist LLM
7. Build DesignFile model from LLM result + dependencies + metadata (including design_hash)
8. Validate token budget
9. Serialize and write design file
10. Refresh parent `.aindex` Child Map entry with frontmatter description

When building the `DesignFileRequest`, the function SHALL pass `available_concepts` to the request if provided.

#### Scenario: New file gets design file
- **WHEN** `update_file()` is called for a file with no existing design file
- **THEN** a design file SHALL be created at the mirror path via full Archivist LLM generation

#### Scenario: Unchanged file skipped
- **WHEN** `update_file()` is called for a file whose content hash matches the stored hash
- **THEN** no LLM call SHALL be made and the function SHALL return UNCHANGED

#### Scenario: Agent-updated file gets footer refresh only
- **WHEN** `update_file()` is called for a file where both source and design file changed
- **THEN** only the metadata footer hashes SHALL be refreshed (no LLM call)

#### Scenario: Footer-less agent-authored file
- **WHEN** `update_file()` is called for a file with an existing design file but no metadata footer
- **THEN** the system SHALL add the footer with current hashes without calling the LLM

#### Scenario: Content-only change uses lightweight prompt
- **WHEN** `update_file()` is called for a file where content changed but interface is unchanged
- **THEN** the LLM SHALL be called (CONTENT_ONLY change level)

#### Scenario: Non-code file content change
- **WHEN** `update_file()` is called for a non-code file whose content changed
- **THEN** the LLM SHALL be called with CONTENT_CHANGED change level

#### Scenario: Interface change triggers full regeneration
- **WHEN** `update_file()` is called for a file whose interface hash changed
- **THEN** the LLM SHALL be called for full design file regeneration

#### Scenario: File outside scope skipped
- **WHEN** `update_file()` is called for a file outside `scope_root`
- **THEN** no processing SHALL occur

#### Scenario: Parent .aindex refreshed
- **WHEN** `update_file()` successfully creates or updates a design file
- **THEN** the parent directory's `.aindex` Child Map entry SHALL be updated with the description from the design file frontmatter

#### Scenario: Available concepts passed to request
- **WHEN** `update_file()` is called with `available_concepts=["JWT Auth", "Rate Limiting"]`
- **THEN** the `DesignFileRequest` SHALL include `available_concepts=["JWT Auth", "Rate Limiting"]`

### Requirement: update_project function
The system SHALL provide `async update_project(project_root, config, archivist, progress_callback?) -> UpdateStats` that updates all design files for the project.

The pipeline SHALL:
1. Create IgnoreMatcher (includes `.lexignore`)
2. Discover all source files within `scope_root`
3. Filter: skip `.lexibrary/` contents, binary files, files outside scope
4. Build concept name list from `.lexibrary/concepts/` if the directory exists
5. For each file: call `update_file()` with `available_concepts` (sequential)
6. After all files: call `generate_start_here()`
7. Return UpdateStats

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
- **THEN** `UpdateStats` SHALL accurately reflect counts for scanned, unchanged, agent_updated, updated, created, failed, aindex_refreshed, and token_budget_warnings

#### Scenario: Concept names loaded for pipeline
- **WHEN** `update_project()` runs and `.lexibrary/concepts/` contains 3 concept files
- **THEN** all `update_file()` calls SHALL receive `available_concepts` with 3 concept names

#### Scenario: No concepts directory
- **WHEN** `update_project()` runs and `.lexibrary/concepts/` doesn't exist
- **THEN** `update_file()` calls SHALL receive `available_concepts=None`
