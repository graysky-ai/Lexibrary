## MODIFIED Requirements

### Requirement: lexi help lists only agent commands
The `lexi --help` output SHALL list only agent-facing commands: `lookup`, `describe`, `concepts`, `concept`, `conventions`, `convention`, `stack`, `search`, `validate`, `status`, `help`. It SHALL NOT list `index`.

#### Scenario: lexi help shows agent commands
- **WHEN** running `lexi --help`
- **THEN** the output SHALL list `lookup`, `describe`, `concepts`, `concept`, `conventions`, `convention`, `stack`, `search`, `validate`, `status`, `help`

#### Scenario: lexi help does NOT show maintenance commands
- **WHEN** running `lexi --help`
- **THEN** the output SHALL NOT contain `init`, `update`, `index`, `setup`, `sweep`, or `daemon`

### Requirement: Lookup command returns design file
`lexi lookup <file>` SHALL return the design file content for a source file, followed by an `## Applicable Conventions` section listing inherited conventions from `ConventionIndex`.
- SHALL check scope: if file is outside `scope_root`, print message and exit
- SHALL compute mirror path and read the design file
- If design file exists → print its content via Rich Console
- If design file doesn't exist → suggest running `lexictl update <file>`
- SHALL check staleness: if source_hash differs from current file hash, print warning before content
- SHALL query `ConventionIndex.find_by_scope_limited()` for applicable conventions using the configured display limit
- If any conventions are found → append an `## Applicable Conventions` section grouped by scope
- If no conventions exist → no extra section appended
- Draft conventions SHALL be marked with `[draft]`
- If conventions are truncated → append truncation notice

#### Scenario: Lookup existing design file
- **WHEN** `lexi lookup src/foo.py` is run and a design file exists
- **THEN** the design file content SHALL be printed

#### Scenario: Lookup missing design file
- **WHEN** `lexi lookup src/foo.py` is run and no design file exists
- **THEN** the system SHALL suggest running `lexictl update src/foo.py`

#### Scenario: Lookup shows staleness warning
- **WHEN** `lexi lookup src/foo.py` is run and the source file has changed since the design file was generated
- **THEN** a staleness warning SHALL be displayed before the content, suggesting `lexictl update`

#### Scenario: Lookup outside scope_root
- **WHEN** `lexi lookup scripts/deploy.sh` is run and `scripts/` is outside scope_root
- **THEN** the system SHALL print a message indicating the file is outside scope_root

#### Scenario: Lookup shows inherited conventions
- **WHEN** `lexi lookup src/payments/processor.py` is run and conventions exist with matching scopes
- **THEN** the output includes an "## Applicable Conventions" section with conventions grouped by scope

#### Scenario: Lookup with no conventions
- **WHEN** `lexi lookup src/utils/helpers.py` is run and no conventions match
- **THEN** no extra conventions section is appended

#### Scenario: Lookup shows draft marker
- **WHEN** `lexi lookup src/auth/login.py` is run and a draft convention applies
- **THEN** the convention SHALL be displayed with a `[draft]` marker

### Requirement: lexi help content reflects rebalanced commands
The `lexi help` command output SHALL organize commands into sections that reflect the rebalanced CLI. The "Inspection & Annotation" section SHALL contain `lexi status`, `lexi validate`, and `lexi describe`. The "Knowledge Management" section SHALL contain `lexi concepts`, `lexi concept`, `lexi conventions`, `lexi convention`, and `lexi stack`.

#### Scenario: Help shows Knowledge Management section
- **WHEN** running `lexi help`
- **THEN** the output SHALL contain a section listing `lexi conventions` and `lexi convention` alongside concepts and stack commands

#### Scenario: Help does NOT reference lexi index
- **WHEN** running `lexi help`
- **THEN** the output SHALL NOT contain `lexi index`

#### Scenario: Help shows convention workflows
- **WHEN** running `lexi help`
- **THEN** the "Common Workflows" panel SHALL include guidance on creating and managing conventions
