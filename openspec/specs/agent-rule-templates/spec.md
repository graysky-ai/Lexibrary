# agent-rule-templates Specification

## Purpose
TBD - created by archiving change agent-rules-iwh. Update Purpose after archive.
## Requirements
### Requirement: Core rule content
The system SHALL provide `get_core_rules() -> str` in `src/lexibrary/init/rules/base.py` returning shared Lexibrary rules applicable to all agent environments. The rules SHALL instruct agents to:
- Read `.lexibrary/START_HERE.md` at session start
- Check for `.iwh` signals when entering directories — read, act, delete
- Run `lexi lookup <file>` before editing
- Update design files directly after editing (set `updated_by: agent`)
- Run `lexi concepts <topic>` before architectural decisions
- Run `lexi stack search` before debugging; `lexi stack post` after solving non-trivial bugs
- Create `.iwh` if leaving work incomplete; do not create if work is clean
- Never run `lexictl` commands — maintenance operations only

#### Scenario: Core rules contain key instructions
- **WHEN** calling `get_core_rules()`
- **THEN** the returned string SHALL contain references to `START_HERE.md`, `.iwh`, `lexi lookup`, `lexi concepts`, `lexi stack`, and design file updates

#### Scenario: No lexictl references in agent instructions
- **WHEN** calling `get_core_rules()`
- **THEN** the returned string SHALL contain a prohibition against running `lexictl` commands and SHALL NOT instruct agents to run `lexictl update`, `lexictl validate`, or `lexictl status`

### Requirement: Orient skill content
The system SHALL provide `get_orient_skill_content() -> str` in `base.py` returning content for a `/lexi-orient` skill that reads `START_HERE.md`, checks for project-root `.iwh`, and runs `lexi status`.

#### Scenario: Orient skill includes session start actions
- **WHEN** calling `get_orient_skill_content()`
- **THEN** the returned string SHALL include instructions to read `START_HERE.md`, check `.lexibrary/.iwh`, and display library status

### Requirement: Search skill content
The system SHALL provide `get_search_skill_content() -> str` in `base.py` returning content for a `/lexi-search` skill that wraps `lexi search` with richer context.

#### Scenario: Search skill wraps lexi search
- **WHEN** calling `get_search_skill_content()`
- **THEN** the returned string SHALL include instructions to run `lexi search` combining concept lookup, Stack search, and design file results

### Requirement: Claude Code rule generation
The system SHALL provide `generate_claude_rules(project_root: Path) -> list[Path]` in `src/lexibrary/init/rules/claude.py` that generates:
- `CLAUDE.md` — append/update a marker-delimited Lexibrary section with core rules
- `.claude/commands/lexi-orient.md` — orient command file
- `.claude/commands/lexi-search.md` — search command file

#### Scenario: Creates CLAUDE.md from scratch
- **WHEN** calling `generate_claude_rules()` where no `CLAUDE.md` exists
- **THEN** a `CLAUDE.md` SHALL be created containing the Lexibrary section between `<!-- lexibrary:start -->` and `<!-- lexibrary:end -->` markers

#### Scenario: Appends to existing CLAUDE.md without markers
- **WHEN** calling `generate_claude_rules()` where `CLAUDE.md` exists but has no Lexibrary markers
- **THEN** the Lexibrary section SHALL be appended with markers, and existing content SHALL be preserved

#### Scenario: Updates existing marked section
- **WHEN** calling `generate_claude_rules()` where `CLAUDE.md` exists with markers and old content between them
- **THEN** only the content between markers SHALL be replaced; content outside markers SHALL be preserved

#### Scenario: Creates command files
- **WHEN** calling `generate_claude_rules()`
- **THEN** `.claude/commands/lexi-orient.md` and `.claude/commands/lexi-search.md` SHALL be created with skill content

#### Scenario: Command files overwritten on update
- **WHEN** calling `generate_claude_rules()` where command files already exist with old content
- **THEN** command files SHALL be overwritten with current content

### Requirement: Cursor rule generation
The system SHALL provide `generate_cursor_rules(project_root: Path) -> list[Path]` in `src/lexibrary/init/rules/cursor.py` that generates:
- `.cursor/rules/lexibrary.mdc` — MDC rules file with YAML frontmatter (`alwaysApply: true`)
- `.cursor/skills/lexi.md` — combined skills file

#### Scenario: Creates MDC rules file
- **WHEN** calling `generate_cursor_rules()`
- **THEN** `.cursor/rules/lexibrary.mdc` SHALL exist with YAML frontmatter containing `description`, `globs`, and `alwaysApply: true`, followed by core rules

#### Scenario: Creates combined skills file
- **WHEN** calling `generate_cursor_rules()`
- **THEN** `.cursor/skills/lexi.md` SHALL exist with combined orient and search skill content

### Requirement: Codex rule generation
The system SHALL provide `generate_codex_rules(project_root: Path) -> list[Path]` in `src/lexibrary/init/rules/codex.py` that generates:
- `AGENTS.md` — append/update a marker-delimited Lexibrary section with core rules and embedded skills

#### Scenario: Creates AGENTS.md from scratch
- **WHEN** calling `generate_codex_rules()` where no `AGENTS.md` exists
- **THEN** an `AGENTS.md` SHALL be created containing the Lexibrary section between markers

#### Scenario: Appends to existing AGENTS.md
- **WHEN** calling `generate_codex_rules()` where `AGENTS.md` exists without markers
- **THEN** the Lexibrary section SHALL be appended with markers, and existing content SHALL be preserved

#### Scenario: Updates existing marked section
- **WHEN** calling `generate_codex_rules()` where `AGENTS.md` exists with markers
- **THEN** only the content between markers SHALL be replaced

### Requirement: Rule generation public API
The system SHALL provide in `src/lexibrary/init/rules/__init__.py`:
- `generate_rules(project_root: Path, environments: list[str]) -> dict[str, list[Path]]` — generates rules for specified environments, returning a mapping of environment name to list of created file paths
- `supported_environments() -> list[str]` — returns `["claude", "cursor", "codex"]`

#### Scenario: Generate for single environment
- **WHEN** calling `generate_rules(root, ["claude"])`
- **THEN** it SHALL return `{"claude": [list of created paths]}`

#### Scenario: Generate for multiple environments
- **WHEN** calling `generate_rules(root, ["claude", "cursor"])`
- **THEN** it SHALL return results for both environments

#### Scenario: Unsupported environment raises error
- **WHEN** calling `generate_rules(root, ["vscode"])`
- **THEN** it SHALL raise a `ValueError`

#### Scenario: Supported environments list
- **WHEN** calling `supported_environments()`
- **THEN** it SHALL return a list containing `"claude"`, `"cursor"`, and `"codex"`

