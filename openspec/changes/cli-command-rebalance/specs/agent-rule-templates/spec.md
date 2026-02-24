## MODIFIED Requirements

### Requirement: Core rule content
The system SHALL provide `get_core_rules() -> str` in `src/lexibrary/init/rules/base.py` returning shared Lexibrary rules applicable to all agent environments. The rules SHALL instruct agents to:
- Read `.lexibrary/START_HERE.md` at session start
- Check for `.iwh` signals when entering directories — read, act, delete
- Run `lexi lookup <file>` before editing
- Update design files directly after editing (set `updated_by: agent`)
- Run `lexi validate` after editing to check for broken links or stale artifacts
- Run `lexi concepts <topic>` before architectural decisions
- Run `lexi stack search` before debugging; `lexi stack post` after solving non-trivial bugs
- Create `.iwh` if leaving work incomplete; do not create if work is clean
- Never run `lexictl` commands — maintenance operations only

#### Scenario: Core rules contain key instructions
- **WHEN** calling `get_core_rules()`
- **THEN** the returned string SHALL contain references to `START_HERE.md`, `.iwh`, `lexi lookup`, `lexi concepts`, `lexi stack`, `lexi validate`, and design file updates

#### Scenario: Core rules include validate recommendation
- **WHEN** calling `get_core_rules()`
- **THEN** the returned string SHALL contain an instruction to run `lexi validate` after editing files

#### Scenario: No lexictl references in agent instructions
- **WHEN** calling `get_core_rules()`
- **THEN** the returned string SHALL contain a prohibition against running `lexictl` commands and SHALL NOT instruct agents to run any `lexictl` subcommand

#### Scenario: No lexi index references in agent instructions
- **WHEN** calling `get_core_rules()`
- **THEN** the returned string SHALL NOT contain `lexi index`

### Requirement: Orient skill content
The system SHALL provide `get_orient_skill_content() -> str` in `base.py` returning content for a `/lexi-orient` skill that reads `START_HERE.md`, checks for project-root `.iwh`, and runs `lexi status`.

#### Scenario: Orient skill includes session start actions
- **WHEN** calling `get_orient_skill_content()`
- **THEN** the returned string SHALL include instructions to read `START_HERE.md`, check `.lexibrary/.iwh`, and run `lexi status`

#### Scenario: Orient skill does not reference lexi index
- **WHEN** calling `get_orient_skill_content()`
- **THEN** the returned string SHALL NOT contain `lexi index`
