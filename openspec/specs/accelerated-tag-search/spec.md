# accelerated-tag-search Specification

## Purpose
TBD - created by archiving change phase-10e-linkgraph-cli. Update Purpose after archive.
## Requirements
### Requirement: Tag search uses index-accelerated lookup when available
When a link graph index is available, `lexi search --tag <t>` SHALL query the `tags` table joined with `artifacts` for O(1) tag lookup instead of scanning all artifact files. Results SHALL be grouped by artifact kind (concepts, design files, Stack posts).

#### Scenario: Tag search with index returns grouped results
- **WHEN** running `lexi search --tag auth` and the link graph index contains tagged artifacts
- **THEN** results SHALL be returned grouped by artifact kind using data from the tags table

#### Scenario: Tag search with index is case-insensitive
- **WHEN** running `lexi search --tag Auth` and artifacts are tagged with `auth`
- **THEN** the tag SHALL match case-insensitively

#### Scenario: Tag search with index returns all matching types
- **WHEN** running `lexi search --tag security` and concepts, design files, and Stack posts all have the `security` tag
- **THEN** results from all three types SHALL appear in their respective groups

### Requirement: Tag search falls back to file scanning when index is unavailable
When the link graph index is not available (missing, corrupt, or schema mismatch), `lexi search --tag <t>` SHALL fall back to the existing file-scanning implementation that reads YAML frontmatter from all artifact files.

#### Scenario: Tag search without index uses file scanning
- **WHEN** running `lexi search --tag auth` and `.lexibrary/index.db` does not exist
- **THEN** the search SHALL use the existing file-scanning code paths (ConceptIndex.by_tag, design file frontmatter scan, StackIndex.by_tag)

#### Scenario: Tag search with corrupt index falls back
- **WHEN** running `lexi search --tag auth` and `.lexibrary/index.db` is corrupt
- **THEN** the search SHALL fall back to file-scanning and return results normally

### Requirement: Tag search with scope filter combines tag and scope
When both `--tag` and `--scope` are provided, the accelerated tag search SHALL apply both filters. The scope filter SHALL be applied after the tag lookup.

#### Scenario: Tag and scope combined with index
- **WHEN** running `lexi search --tag auth --scope src/api/` and the index has matching tagged artifacts
- **THEN** only artifacts with tag `auth` whose path starts with `src/api/` SHALL be returned

#### Scenario: Tag and scope combined without index
- **WHEN** running `lexi search --tag auth --scope src/api/` and the index is unavailable
- **THEN** the existing file-scanning path SHALL apply both tag and scope filters

### Requirement: Accelerated tag search returns title metadata
When using the index-accelerated path, tag search results SHALL include the `title` field from the `artifacts` table, enabling rich result display without reading individual artifact files.

#### Scenario: Tag results include titles from index
- **WHEN** `lexi search --tag auth` uses the index-accelerated path
- **THEN** each result SHALL display its title from the artifacts table (concept title, design file description, or Stack post title)

