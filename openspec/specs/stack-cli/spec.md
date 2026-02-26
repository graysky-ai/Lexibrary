# stack-cli Specification

## Purpose
TBD - created by archiving change the-stack. Update Purpose after archive.
## Requirements
### Requirement: Stack command group
The system SHALL provide a `lexi stack` command group in `cli.py` using a Typer sub-app. All stack commands SHALL use `rich.console.Console` for output.

#### Scenario: Stack help
- **WHEN** running `lexi stack --help`
- **THEN** the output SHALL list all available stack sub-commands

### Requirement: Stack post command
`lexi stack post --title "..." --tag <t> [--tag <t>...] [--bead <id>] [--file <f>...] [--concept <c>...]` SHALL create a new stack post file with auto-assigned ID. Minimum required: `--title` and at least one `--tag`. The command SHALL output the created file path and guidance to fill in the Problem/Evidence sections.

#### Scenario: Create post with required flags
- **WHEN** running `lexi stack post --title "Bug in auth" --tag auth`
- **THEN** a file SHALL be created at `.lexibrary/stack/ST-NNN-bug-in-auth.md` with auto-assigned ID and the command SHALL print the file path

#### Scenario: Create post with all flags
- **WHEN** running `lexi stack post --title "Bug" --tag auth --bead BEAD-1 --file src/auth.py --concept Authentication`
- **THEN** the post SHALL include the bead, file ref, and concept ref in frontmatter

#### Scenario: Create post without title fails
- **WHEN** running `lexi stack post --tag auth` (no --title)
- **THEN** the command SHALL exit with an error

#### Scenario: Create post without tag fails
- **WHEN** running `lexi stack post --title "Bug"` (no --tag)
- **THEN** the command SHALL exit with an error

### Requirement: Stack search command
`lexi stack search <query> [--tag <t>] [--scope <path>] [--status <s>] [--concept <c>]` SHALL search stack posts and display results in a compact format showing ID, status, votes, title, tags, and refs.

#### Scenario: Search by query
- **WHEN** running `lexi stack search "timezone"`
- **THEN** matching posts SHALL be displayed with ID, status badge, vote count, and title

#### Scenario: Search with tag filter
- **WHEN** running `lexi stack search "timezone" --tag datetime`
- **THEN** only posts matching both the query and the tag SHALL be displayed

#### Scenario: Search with scope filter
- **WHEN** running `lexi stack search --scope src/models/`
- **THEN** only posts referencing files under `src/models/` SHALL be displayed

#### Scenario: Search with no results
- **WHEN** running `lexi stack search "nonexistent"`
- **THEN** the output SHALL indicate no posts were found

### Requirement: Stack answer command
`lexi stack answer <post-id> --body "..."` SHALL append a new answer to the specified post and print confirmation with the answer number.

#### Scenario: Add answer to existing post
- **WHEN** running `lexi stack answer ST-001 --body "Solution text"`
- **THEN** a new answer SHALL be appended and the output SHALL confirm the answer number

#### Scenario: Add answer to nonexistent post
- **WHEN** running `lexi stack answer ST-999 --body "Solution"`
- **THEN** the command SHALL print an error indicating the post was not found

### Requirement: Stack vote command
`lexi stack vote <post-id> [--answer <n>] up|down [--comment "..."]` SHALL record a vote on a post or answer. Downvotes SHALL require `--comment`.

#### Scenario: Upvote post
- **WHEN** running `lexi stack vote ST-001 up`
- **THEN** the post's vote count SHALL be incremented and the new count displayed

#### Scenario: Downvote answer with comment
- **WHEN** running `lexi stack vote ST-001 --answer 2 down --comment "Unreliable approach"`
- **THEN** A2's vote count SHALL be decremented and the comment recorded

#### Scenario: Downvote without comment fails
- **WHEN** running `lexi stack vote ST-001 down` (no --comment)
- **THEN** the command SHALL print an error requiring a comment for downvotes

### Requirement: Stack accept command
`lexi stack accept <post-id> --answer <n>` SHALL mark the specified answer as accepted and set the post status to `resolved`.

#### Scenario: Accept answer
- **WHEN** running `lexi stack accept ST-001 --answer 1`
- **THEN** A1 SHALL be marked accepted and the post status set to `resolved`

### Requirement: Stack view command
`lexi stack view <post-id>` SHALL display the full post content with formatted output including title, status, votes, tags, refs, problem, evidence, and all answers with comments.

#### Scenario: View existing post
- **WHEN** running `lexi stack view ST-001`
- **THEN** the full post SHALL be displayed with formatted sections

#### Scenario: View nonexistent post
- **WHEN** running `lexi stack view ST-999`
- **THEN** the command SHALL print an error indicating the post was not found

### Requirement: Stack list command
`lexi stack list [--status <s>] [--tag <t>]` SHALL display a compact list of all stack posts, optionally filtered by status or tag.

#### Scenario: List all posts
- **WHEN** running `lexi stack list`
- **THEN** all posts SHALL be listed with ID, status, votes, and title

#### Scenario: List filtered by status
- **WHEN** running `lexi stack list --status open`
- **THEN** only posts with `status="open"` SHALL be listed

#### Scenario: List filtered by tag
- **WHEN** running `lexi stack list --tag auth`
- **THEN** only posts with the "auth" tag SHALL be listed

### Requirement: Stack mark-outdated command
`lexi stack mark-outdated <post-id>` SHALL mark a Stack post as outdated by calling `mark_outdated()` from `stack/mutations.py` and printing a confirmation message.

#### Scenario: Mark post as outdated
- **WHEN** running `lexi stack mark-outdated ST-001`
- **THEN** the post SHALL have `status="outdated"` and a confirmation message SHALL be printed

#### Scenario: Mark nonexistent post as outdated
- **WHEN** running `lexi stack mark-outdated ST-999` and no such post exists
- **THEN** the command SHALL print an error indicating the post was not found

### Requirement: Stack duplicate command
`lexi stack duplicate <post-id> --of <original-id>` SHALL mark a Stack post as a duplicate of another by calling `mark_duplicate()` from `stack/mutations.py` and printing a confirmation message.

#### Scenario: Mark post as duplicate
- **WHEN** running `lexi stack duplicate ST-003 --of ST-001`
- **THEN** the post SHALL have `status="duplicate"` and `duplicate_of="ST-001"` and a confirmation message SHALL be printed

#### Scenario: Duplicate without --of flag fails
- **WHEN** running `lexi stack duplicate ST-003` without `--of`
- **THEN** the command SHALL exit with an error requiring the `--of` flag

#### Scenario: Mark nonexistent post as duplicate
- **WHEN** running `lexi stack duplicate ST-999 --of ST-001` and ST-999 does not exist
- **THEN** the command SHALL print an error indicating the post was not found

