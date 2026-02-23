## MODIFIED Requirements

### Requirement: Status collects artifact counts by type
The `lexictl status` command SHALL display counts of tracked design files, concepts (broken down by status: active, deprecated, draft), Stack posts (broken down by status: open, resolved), and link graph health (artifact count, link count, build timestamp). The link graph line SHALL appear after the Stack line and before the Issues line.

#### Scenario: Status shows design file count with stale breakdown
- **WHEN** the library contains 47 design files and 3 have stale source hashes
- **THEN** the output includes "Files: 47 tracked, 3 stale"

#### Scenario: Status shows concept count with status breakdown
- **WHEN** the library contains 12 active, 1 deprecated, and 2 draft concepts
- **THEN** the output includes "Concepts: 12 active, 1 deprecated, 2 draft"

#### Scenario: Status shows Stack post count with status breakdown
- **WHEN** the library contains 5 resolved and 3 open Stack posts
- **THEN** the output includes "Stack: 8 posts (5 resolved, 3 open)"

#### Scenario: Status shows link graph health when index exists
- **WHEN** the library has an index.db with 245 artifacts, 1203 links, built at 2026-02-22T14:30:00Z
- **THEN** the output includes "Link graph: 245 artifacts, 1,203 links (built 2026-02-22T14:30:00Z)"

#### Scenario: Status shows link graph not built when index missing
- **WHEN** the library has no index.db file
- **THEN** the output includes "Link graph: not built (run lexictl update to create)"
