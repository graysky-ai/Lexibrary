# linkgraph-validation Specification

## Purpose
TBD - created by archiving change phase-10f-linkgraph-validation. Update Purpose after archive.
## Requirements
### Requirement: check_bidirectional_deps validates dependency consistency via link graph
The `check_bidirectional_deps` function SHALL open the link graph index at `lexibrary_dir / "index.db"` and compare design file dependency lists against `ast_import` links in the graph. For each design file, the function SHALL parse the `## Dependencies` section to get listed dependencies, then query the graph for actual `ast_import` outbound links from the corresponding source file. Mismatches in either direction SHALL produce info-severity `ValidationIssue` entries with check name `"bidirectional_deps"`. If the index does not exist or cannot be opened, the function SHALL return an empty list without error.

#### Scenario: All dependencies are consistent
- **WHEN** every dependency listed in design files has a corresponding `ast_import` link in the graph, and every `ast_import` link in the graph is listed in the design file dependencies
- **THEN** no issues are returned

#### Scenario: Design file lists dependency not found in graph
- **WHEN** a design file for `src/api/auth.py` lists `src/utils/crypto.py` as a dependency, but the link graph has no `ast_import` link from `src/api/auth.py` to `src/utils/crypto.py`
- **THEN** an info issue is returned with check="bidirectional_deps", message indicating the dependency is listed in the design file but not found in the link graph, and suggestion noting the index may be stale

#### Scenario: Graph link exists but not listed in design file
- **WHEN** the link graph has an `ast_import` link from `src/api/auth.py` to `src/models/user.py`, but the design file for `src/api/auth.py` does not list `src/models/user.py` in its dependencies
- **THEN** an info issue is returned with check="bidirectional_deps", message indicating the import exists in the graph but is not listed in the design file

#### Scenario: Index does not exist
- **WHEN** `.lexibrary/index.db` does not exist
- **THEN** the function returns an empty list without raising an exception

#### Scenario: Index is corrupt or has wrong schema version
- **WHEN** `.lexibrary/index.db` exists but is corrupt or has a schema version mismatch
- **THEN** the function returns an empty list without raising an exception

### Requirement: check_dangling_links detects graph links to non-existent files
The `check_dangling_links` function SHALL open the link graph index and query all artifacts. For each artifact whose `kind` is `"source"`, `"design"`, `"concept"`, or `"stack"`, it SHALL verify the file at `artifact.path` (resolved relative to `project_root`) exists on disk. Artifacts whose backing files are missing SHALL produce info-severity `ValidationIssue` entries with check name `"dangling_links"`. If the index does not exist or cannot be opened, the function SHALL return an empty list.

#### Scenario: All graph artifacts exist on disk
- **WHEN** every artifact in the link graph has a corresponding file on disk
- **THEN** no issues are returned

#### Scenario: Artifact in graph references deleted file
- **WHEN** the link graph contains an artifact for `src/old_module.py` but that file has been deleted
- **THEN** an info issue is returned with check="dangling_links" and message indicating the artifact references a file that no longer exists

#### Scenario: Convention artifacts are skipped
- **WHEN** the link graph contains convention artifacts with synthetic paths (e.g., `src/api::convention::0`)
- **THEN** convention artifacts are not checked for file existence (they have no backing file)

#### Scenario: Index does not exist
- **WHEN** `.lexibrary/index.db` does not exist
- **THEN** the function returns an empty list without raising an exception

### Requirement: check_orphan_artifacts detects index entries for deleted files
The `check_orphan_artifacts` function SHALL open the link graph index and query all artifacts with `kind` in (`"source"`, `"design"`, `"concept"`, `"stack"`). For each artifact, it SHALL verify the backing file exists on disk. Artifacts whose files have been deleted SHALL produce info-severity `ValidationIssue` entries with check name `"orphan_artifacts"` and a suggestion to rebuild the index. If the index does not exist or cannot be opened, the function SHALL return an empty list.

#### Scenario: No orphan artifacts
- **WHEN** all artifacts in the index have existing backing files
- **THEN** no issues are returned

#### Scenario: Source file deleted but still in index
- **WHEN** `src/services/deprecated.py` was deleted but the index still has an artifact entry for it
- **THEN** an info issue is returned with check="orphan_artifacts", artifact=`src/services/deprecated.py`, and suggestion to run `lexictl update` to rebuild the index

#### Scenario: Index does not exist
- **WHEN** `.lexibrary/index.db` does not exist
- **THEN** the function returns an empty list without raising an exception

### Requirement: All link-graph checks are read-only
All three link-graph validation check functions SHALL operate in read-only mode. They SHALL NOT modify any files on disk, insert or delete rows in the link graph database, or trigger any index rebuild. This upholds D-047.

#### Scenario: Validation does not modify the index
- **WHEN** running any link-graph validation check
- **THEN** the `index.db` file's modification time and content are unchanged after the check completes

### Requirement: All link-graph checks use info severity
All issues produced by `check_bidirectional_deps`, `check_dangling_links`, and `check_orphan_artifacts` SHALL use `"info"` severity. They SHALL NOT produce `"error"` or `"warning"` severity issues because the link graph index may be stale.

#### Scenario: Link graph check never produces errors or warnings
- **WHEN** running any link-graph validation check with a stale or inconsistent index
- **THEN** all returned issues have severity="info"

