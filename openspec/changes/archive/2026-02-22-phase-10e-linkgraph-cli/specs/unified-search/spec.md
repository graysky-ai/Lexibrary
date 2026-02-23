## MODIFIED Requirements

### Requirement: Unified search command
`lexi search <query> [--tag <t>] [--scope <path>]` SHALL search across concepts (via `ConceptIndex`), design files (via YAML frontmatter scan), and Stack posts (via `StackIndex`). When a link graph index is available, tag queries SHALL use the index-accelerated `tags` table lookup and free-text queries SHALL use FTS5 ranked search. When the index is unavailable, the command SHALL fall back to file-scanning for all query types. Results SHALL be grouped under `-- Concepts --`, `-- Design Files --`, and `-- Stack --` headers. Groups with no matches SHALL be omitted.

#### Scenario: Search by tag across all types
- **WHEN** running `lexi search --tag auth` and matching artifacts exist in concepts, design files, and Stack posts
- **THEN** results SHALL be grouped by type with matches from all three artifact types

#### Scenario: Free-text search with index
- **WHEN** running `lexi search "timezone"` and a valid link graph index exists
- **THEN** the search SHALL use FTS5 and return relevance-ranked results across all artifact types

#### Scenario: Free-text search without index
- **WHEN** running `lexi search "timezone"` and no link graph index exists
- **THEN** the search SHALL fall back to file-scanning and match titles/summaries/bodies across all artifact types

#### Scenario: Search with no results
- **WHEN** running `lexi search "nonexistent-query"`
- **THEN** the output SHALL indicate no results were found

#### Scenario: Search omits empty groups
- **WHEN** running `lexi search --tag auth` and no Stack posts match
- **THEN** the `-- Stack --` group SHALL be omitted from output

### Requirement: Design file tag search
When the link graph index is unavailable, the unified search SHALL scan design file YAML frontmatter `tags` fields for tag-based queries. For free-text queries without an index, it SHALL match against the `description` field in frontmatter. When the index is available, both tag and free-text queries SHALL use the index instead of file scanning.

#### Scenario: Match design file by tag without index
- **WHEN** `lexi search --tag security` is run without a link graph index and a design file has `tags: [security, auth]`
- **THEN** the design file SHALL appear in the `-- Design Files --` group via file scanning

#### Scenario: Match design file by tag with index
- **WHEN** `lexi search --tag security` is run with a valid link graph index and the tags table contains a design file artifact with tag `security`
- **THEN** the design file SHALL appear in the `-- Design Files --` group via index lookup

#### Scenario: Match design file by description without index
- **WHEN** `lexi search "authentication"` is run without a link graph index and a design file has `description: "Handles authentication flow"`
- **THEN** the design file SHALL appear in results via file scanning

### Requirement: Concept search integration
The unified search SHALL use the existing `ConceptIndex` for concept searches when the link graph index is unavailable. Tag queries SHALL use `ConceptIndex.by_tag()`. Free-text queries SHALL use `ConceptIndex.search()`. When the link graph index is available, both tag and free-text queries SHALL use the index for concepts.

#### Scenario: Concept search via unified command without index
- **WHEN** `lexi search "JWT"` is run without a link graph index and a concept named "JWTTokens" exists
- **THEN** the concept SHALL appear in the `-- Concepts --` group via ConceptIndex

#### Scenario: Concept search via unified command with index
- **WHEN** `lexi search "JWT"` is run with a valid link graph index and the FTS table contains a concept matching "JWT"
- **THEN** the concept SHALL appear in the `-- Concepts --` group via FTS5

## ADDED Requirements

### Requirement: unified_search accepts optional link_graph parameter
The `unified_search()` function SHALL accept an optional `link_graph` parameter (type `LinkGraph | None`, default `None`). When not `None`, the function SHALL use index-accelerated code paths for tag and free-text queries. When `None`, the function SHALL use existing file-scanning code paths.

#### Scenario: unified_search called with link_graph
- **WHEN** `unified_search(project_root, tag="auth", link_graph=graph)` is called with a valid `LinkGraph` instance
- **THEN** the function SHALL use the index-accelerated tag lookup

#### Scenario: unified_search called without link_graph
- **WHEN** `unified_search(project_root, tag="auth")` is called without a `link_graph` argument
- **THEN** the function SHALL use the existing file-scanning code paths
