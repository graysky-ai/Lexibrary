## ADDED Requirements

### Requirement: Update command generates design files
`lexi update [<path>]` SHALL generate or refresh design files for changed source files.
- If `path` is a file → update that single file's design file
- If `path` is a directory → update all files in that subtree within scope_root
- If no path → update all files in the project and regenerate START_HERE.md
- SHALL display a Rich progress bar for multi-file updates
- SHALL print summary stats on completion (including agent-updated count)
- SHALL exit with code 0 on success, 1 on any failures

#### Scenario: Update single file
- **WHEN** `lexi update src/foo.py` is run
- **THEN** the system SHALL generate or refresh the design file at `.lexibrary/src/foo.py.md`

#### Scenario: Update directory
- **WHEN** `lexi update src/` is run
- **THEN** the system SHALL update design files for all changed files under `src/` within scope_root

#### Scenario: Update entire project
- **WHEN** `lexi update` is run with no arguments
- **THEN** the system SHALL update all changed files and regenerate START_HERE.md

#### Scenario: No project found
- **WHEN** `lexi update` is run outside a Lexibrary project (no `.lexibrary/`)
- **THEN** the system SHALL print an error and exit with code 1

### Requirement: Lookup command returns design file
`lexi lookup <file>` SHALL return the design file content for a source file.
- SHALL check scope: if file is outside `scope_root`, print message and exit
- SHALL compute mirror path and read the design file
- If design file exists → print its content via Rich Console
- If design file doesn't exist → suggest running `lexi update <file>`
- SHALL check staleness: if source_hash differs from current file hash, print warning before content

#### Scenario: Lookup existing design file
- **WHEN** `lexi lookup src/foo.py` is run and a design file exists
- **THEN** the design file content SHALL be printed

#### Scenario: Lookup missing design file
- **WHEN** `lexi lookup src/foo.py` is run and no design file exists
- **THEN** the system SHALL suggest running `lexi update src/foo.py`

#### Scenario: Lookup shows staleness warning
- **WHEN** `lexi lookup src/foo.py` is run and the source file has changed since the design file was generated
- **THEN** a staleness warning SHALL be displayed before the content

#### Scenario: Lookup outside scope_root
- **WHEN** `lexi lookup scripts/deploy.sh` is run and `scripts/` is outside scope_root
- **THEN** the system SHALL print a message indicating the file is outside scope_root

### Requirement: Describe command updates .aindex billboard
`lexi describe <directory> "<description>"` SHALL update the billboard description in a directory's `.aindex` file.
- SHALL parse the existing `.aindex`
- SHALL update the billboard text
- SHALL re-serialize and write the `.aindex`

#### Scenario: Update directory description
- **WHEN** `lexi describe src/auth "Authentication and authorization services"` is run
- **THEN** the `.aindex` billboard for `src/auth/` SHALL be updated with the new description
