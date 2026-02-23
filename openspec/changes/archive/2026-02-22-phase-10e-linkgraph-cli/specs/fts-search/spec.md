## ADDED Requirements

### Requirement: FTS5-powered full-text search via lexi search
When a link graph index is available, `lexi search <query>` (free-text query without `--tag`) SHALL use FTS5 full-text search to return ranked results across all artifact types. Results SHALL be grouped by artifact kind (concepts, design files, Stack posts) and ordered by FTS5 relevance ranking within each group.

#### Scenario: FTS search returns ranked results
- **WHEN** running `lexi search "authentication"` and the link graph index contains artifacts matching "authentication"
- **THEN** results SHALL be returned grouped by type and ordered by relevance rank within each group

#### Scenario: FTS search matches across artifact types
- **WHEN** running `lexi search "timezone"` and concepts, design files, and Stack posts contain "timezone"
- **THEN** results from all three artifact types SHALL appear in their respective groups

#### Scenario: FTS search uses porter stemming
- **WHEN** running `lexi search "authenticating"` and a concept title contains "authentication"
- **THEN** the concept SHALL match due to FTS5 porter stemming

#### Scenario: FTS search with no matches
- **WHEN** running `lexi search "xyznonexistent"` and no artifacts match
- **THEN** the output SHALL indicate no results were found

### Requirement: FTS search result display includes title and path
FTS search results SHALL display the artifact path, kind, and title (from the `artifacts` table). This enables rich result display without additional file I/O.

#### Scenario: FTS results show title
- **WHEN** FTS search returns a concept with title "Authentication"
- **THEN** the concept appears in the Concepts group showing name "Authentication"

#### Scenario: FTS results show design file source path
- **WHEN** FTS search returns a design file artifact
- **THEN** the design file appears in the Design Files group showing its source file path

#### Scenario: FTS results show Stack post ID and title
- **WHEN** FTS search returns a Stack post
- **THEN** the Stack post appears in the Stack group showing its post ID and title

### Requirement: FTS search falls back to file scanning when index is unavailable
When the link graph index is not available, `lexi search <query>` SHALL fall back to the existing file-scanning free-text search implementation (substring matching against description, source_path, and tags).

#### Scenario: Free-text search without index uses file scanning
- **WHEN** running `lexi search "authentication"` and `.lexibrary/index.db` does not exist
- **THEN** the search SHALL use the existing file-scanning path and return substring-matched results

#### Scenario: Free-text search with index uses FTS
- **WHEN** running `lexi search "authentication"` and `.lexibrary/index.db` exists with valid schema
- **THEN** the search SHALL use FTS5 and return relevance-ranked results

### Requirement: FTS search does not apply to tag-only queries
When `--tag` is provided without a free-text query, the FTS code path SHALL NOT be used. Tag queries use the accelerated tag search capability instead.

#### Scenario: Tag-only query does not use FTS
- **WHEN** running `lexi search --tag auth` with a valid link graph index
- **THEN** the search SHALL use the tag table lookup, not FTS5
