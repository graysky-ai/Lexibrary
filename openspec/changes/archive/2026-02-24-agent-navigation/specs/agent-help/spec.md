## ADDED Requirements

### Requirement: Agent help command
`lexi help` SHALL display structured guidance for coding agents working inside a Lexibrary project. The output SHALL use Rich panels and MUST cover:
1. **Available commands** — grouped by purpose (lookup & navigation, concepts & knowledge, stack Q&A, indexing & maintenance)
2. **Common workflows** — step-by-step patterns for tasks agents frequently perform (e.g., "understand a file", "explore a topic", "ask a question")
3. **Navigation tips** — how to use wikilinks, the link graph, and cross-artifact search

The command SHALL NOT require an initialised project (no `.lexibrary/` needed) — it provides general orientation that is useful even before `lexictl init`.

#### Scenario: Help command displays guidance
- **WHEN** `lexi help` is run
- **THEN** the output SHALL contain Rich-formatted panels with command descriptions, workflow patterns, and navigation tips

#### Scenario: Help works without initialised project
- **WHEN** `lexi help` is run in a directory without `.lexibrary/`
- **THEN** the command SHALL succeed and display the same guidance (no project root required)

#### Scenario: Help uses Rich console
- **WHEN** `lexi help` produces output
- **THEN** all output SHALL be rendered through a Rich Console instance (no bare `print()`)

### Requirement: Help command listed in lexi --help
`lexi help` SHALL appear in the `lexi --help` output alongside other agent-facing commands.

#### Scenario: Help appears in CLI help
- **WHEN** `lexi --help` is run
- **THEN** `help` SHALL be listed as an available command with a brief description

### Requirement: Help content covers all agent commands
The `lexi help` output SHALL reference every registered agent-facing command: `lookup`, `index`, `describe`, `concepts`, `concept`, `stack`, `search`, and `help` itself.

#### Scenario: All commands mentioned
- **WHEN** `lexi help` is run
- **THEN** the output SHALL mention `lookup`, `index`, `describe`, `concepts`, `concept new`, `concept link`, `stack`, and `search`

### Requirement: Help content includes workflow examples
The `lexi help` output SHALL include at least three workflow patterns demonstrating multi-command sequences agents can follow.

#### Scenario: Workflow examples present
- **WHEN** `lexi help` is run
- **THEN** the output SHALL contain at least 3 distinct workflow descriptions with example command sequences
