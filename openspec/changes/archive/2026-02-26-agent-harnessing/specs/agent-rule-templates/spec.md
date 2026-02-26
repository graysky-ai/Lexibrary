## ADDED Requirements

### Requirement: Lookup skill content
The system SHALL provide `get_lookup_skill_content() -> str` in `src/lexibrary/init/rules/base.py` returning content for a `/lexi-lookup` skill that runs `lexi lookup <file>` to see design context for a source file before editing it.

#### Scenario: Lookup skill content available
- **WHEN** calling `get_lookup_skill_content()`
- **THEN** the returned string SHALL contain instructions to run `lexi lookup` with a file argument

### Requirement: Concepts skill content
The system SHALL provide `get_concepts_skill_content() -> str` in `src/lexibrary/init/rules/base.py` returning content for a `/lexi-concepts` skill that runs `lexi concepts [topic]` with guidance on `--tag` and `--all` flags.

#### Scenario: Concepts skill content available
- **WHEN** calling `get_concepts_skill_content()`
- **THEN** the returned string SHALL contain instructions to run `lexi concepts` with topic, `--tag`, and `--all` options

### Requirement: Stack skill content
The system SHALL provide `get_stack_skill_content() -> str` in `src/lexibrary/init/rules/base.py` returning content for a `/lexi-stack` skill with guided prompts for `lexi stack search`, `lexi stack post`, and `lexi stack answer`.

#### Scenario: Stack skill content available
- **WHEN** calling `get_stack_skill_content()`
- **THEN** the returned string SHALL contain instructions for `lexi stack search`, `lexi stack post`, and `lexi stack answer` operations

## MODIFIED Requirements

### Requirement: Claude Code rule generation
The system SHALL provide `generate_claude_rules(project_root: Path) -> list[Path]` in `src/lexibrary/init/rules/claude.py` that generates:
- `CLAUDE.md` — append/update a marker-delimited Lexibrary section with core rules
- `.claude/commands/lexi-orient.md` — orient command file
- `.claude/commands/lexi-search.md` — search command file
- `.claude/commands/lexi-lookup.md` — lookup command file
- `.claude/commands/lexi-concepts.md` — concepts command file
- `.claude/commands/lexi-stack.md` — stack command file

#### Scenario: Creates CLAUDE.md from scratch
- **WHEN** calling `generate_claude_rules()` where no `CLAUDE.md` exists
- **THEN** a `CLAUDE.md` SHALL be created containing the Lexibrary section between `<!-- lexibrary:start -->` and `<!-- lexibrary:end -->` markers

#### Scenario: Appends to existing CLAUDE.md without markers
- **WHEN** calling `generate_claude_rules()` where `CLAUDE.md` exists but has no Lexibrary markers
- **THEN** the Lexibrary section SHALL be appended with markers, and existing content SHALL be preserved

#### Scenario: Updates existing marked section
- **WHEN** calling `generate_claude_rules()` where `CLAUDE.md` exists with markers and old content between them
- **THEN** only the content between markers SHALL be replaced; content outside markers SHALL be preserved

#### Scenario: Creates all command files
- **WHEN** calling `generate_claude_rules()`
- **THEN** `.claude/commands/lexi-orient.md`, `.claude/commands/lexi-search.md`, `.claude/commands/lexi-lookup.md`, `.claude/commands/lexi-concepts.md`, and `.claude/commands/lexi-stack.md` SHALL be created with skill content

#### Scenario: Command files overwritten on update
- **WHEN** calling `generate_claude_rules()` where command files already exist with old content
- **THEN** command files SHALL be overwritten with current content

### Requirement: Cursor rule generation
The system SHALL provide `generate_cursor_rules(project_root: Path) -> list[Path]` in `src/lexibrary/init/rules/cursor.py` that generates:
- `.cursor/rules/lexibrary.mdc` — MDC rules file with YAML frontmatter (`alwaysApply: true`)
- `.cursor/rules/lexibrary-editing.mdc` — MDC rules file scoped to source files (`alwaysApply: false`, glob-triggered)
- `.cursor/skills/lexi.md` — combined skills file (including new lookup, concepts, stack skills)

The editing rule SHALL use glob patterns derived from `config.scope_root` (defaulting to `src`) and instruct agents to run `lexi lookup` before editing and update design files after.

#### Scenario: Creates MDC rules file
- **WHEN** calling `generate_cursor_rules()`
- **THEN** `.cursor/rules/lexibrary.mdc` SHALL exist with YAML frontmatter containing `description`, `globs`, and `alwaysApply: true`, followed by core rules

#### Scenario: Creates editing-scoped MDC rules file
- **WHEN** calling `generate_cursor_rules()`
- **THEN** `.cursor/rules/lexibrary-editing.mdc` SHALL exist with `alwaysApply: false` and `globs` matching source files under `scope_root`

#### Scenario: Editing rule uses config scope_root
- **WHEN** calling `generate_cursor_rules()` with `scope_root` configured as `"lib"`
- **THEN** the editing rule globs SHALL include `"lib/**"`

#### Scenario: Creates combined skills file with all skills
- **WHEN** calling `generate_cursor_rules()`
- **THEN** `.cursor/skills/lexi.md` SHALL exist with orient, search, lookup, concepts, and stack skill content

### Requirement: Codex rule generation
The system SHALL provide `generate_codex_rules(project_root: Path) -> list[Path]` in `src/lexibrary/init/rules/codex.py` that generates:
- `AGENTS.md` — append/update a marker-delimited Lexibrary section with core rules and embedded skills (including new lookup, concepts, stack skills)

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
- `supported_environments() -> list[str]` — returns `["claude", "cursor", "codex", "generic"]`

#### Scenario: Generate for single environment
- **WHEN** calling `generate_rules(root, ["claude"])`
- **THEN** it SHALL return `{"claude": [list of created paths]}`

#### Scenario: Generate for multiple environments
- **WHEN** calling `generate_rules(root, ["claude", "cursor"])`
- **THEN** it SHALL return results for both environments

#### Scenario: Unsupported environment raises error
- **WHEN** calling `generate_rules(root, ["vscode"])`
- **THEN** it SHALL raise a `ValueError`

#### Scenario: Supported environments list includes generic
- **WHEN** calling `supported_environments()`
- **THEN** it SHALL return a list containing `"claude"`, `"cursor"`, `"codex"`, and `"generic"`
