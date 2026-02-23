# library-status Specification

## Purpose
TBD - created by archiving change validation-status. Update Purpose after archive.
## Requirements
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

### Requirement: Status shows issue counts by severity
The `lexi status` command SHALL run a lightweight subset of validation (errors and warnings only, skipping info-severity checks) and display issue counts.

#### Scenario: Status shows error and warning counts
- **WHEN** the library has 0 errors and 3 warnings
- **THEN** the output includes "Issues: 0 errors, 3 warnings"

#### Scenario: Status with errors shows error count
- **WHEN** the library has 2 errors and 1 warning
- **THEN** the output includes "Issues: 2 errors, 1 warning"

### Requirement: Status shows last update timestamp
The `lexi status` command SHALL display the most recent `generated` timestamp from any design file metadata footer, formatted as a relative time (e.g., "2 minutes ago").

#### Scenario: Last updated shows relative time
- **WHEN** the most recent design file was generated 2 minutes ago
- **THEN** the output includes "Updated: 2 minutes ago"

#### Scenario: No design files shows appropriate message
- **WHEN** the library contains no design files
- **THEN** the output includes "Updated: never"

### Requirement: Status suggests validate for details
The default `lexi status` output SHALL end with the message "Run `lexi validate` for details." when there are any issues.

#### Scenario: Status with issues shows validate suggestion
- **WHEN** the library has warnings
- **THEN** the output ends with "Run `lexi validate` for details."

#### Scenario: Status with no issues omits validate suggestion
- **WHEN** the library has no errors or warnings
- **THEN** the validate suggestion is not displayed

### Requirement: Status quiet mode outputs single line
The `lexi status --quiet` flag SHALL output a single line suitable for hooks and CI. When issues exist, the format SHALL be `lexi: N warnings — run \`lexi validate\``. When clean, the format SHALL be `lexi: library healthy`.

#### Scenario: Quiet mode with warnings
- **WHEN** running `lexi status --quiet` with 3 warnings and 0 errors
- **THEN** output is exactly `lexi: 3 warnings — run \`lexi validate\``

#### Scenario: Quiet mode with errors and warnings
- **WHEN** running `lexi status --quiet` with 2 errors and 1 warning
- **THEN** output is exactly `lexi: 2 errors, 1 warning — run \`lexi validate\``

#### Scenario: Quiet mode when healthy
- **WHEN** running `lexi status --quiet` with no errors or warnings
- **THEN** output is exactly `lexi: library healthy`

### Requirement: Status uses same exit codes as validate
The `lexi status` command SHALL use exit code 0 when no errors or warnings exist, exit code 1 when errors exist, and exit code 2 when warnings exist but no errors. This enables `lexi status --quiet` as a CI/hook gate.

#### Scenario: Clean library exits 0
- **WHEN** the library has no issues
- **THEN** exit code is 0

#### Scenario: Library with errors exits 1
- **WHEN** the library has at least one error
- **THEN** exit code is 1

#### Scenario: Library with only warnings exits 2
- **WHEN** the library has warnings but no errors
- **THEN** exit code is 2

### Requirement: Status completes within performance target
The `lexi status` command SHALL complete in under 2 seconds for typical projects by using lightweight parsing (metadata-only for hash checks, frontmatter-only for concept/Stack status) and skipping info-severity checks.

#### Scenario: Status is fast for medium project
- **WHEN** running `lexi status` on a project with ~100 design files, ~20 concepts, and ~10 Stack posts
- **THEN** the command completes in under 2 seconds

