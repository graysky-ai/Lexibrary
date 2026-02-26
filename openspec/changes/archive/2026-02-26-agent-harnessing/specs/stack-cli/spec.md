## ADDED Requirements

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
