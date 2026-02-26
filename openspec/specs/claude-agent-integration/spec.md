# claude-agent-integration Specification

## Purpose
TBD - created by archiving change agent-harnessing. Update Purpose after archive.
## Requirements
### Requirement: Generate Claude settings.json with permissions
The system SHALL provide `_generate_settings_json(project_root: Path) -> Path` in `src/lexibrary/init/rules/claude.py` that generates `.claude/settings.json` with pre-approved `lexi` commands in `permissions.allow` and `lexictl` commands in `permissions.deny`.

The `permissions.allow` list SHALL include:
- `Bash(lexi *)`, `Bash(lexi lookup *)`, `Bash(lexi search *)`, `Bash(lexi concepts *)`, `Bash(lexi concept *)`, `Bash(lexi stack *)`, `Bash(lexi describe *)`, `Bash(lexi validate *)`, `Bash(lexi status *)`, `Bash(lexi help)`, `Bash(lexi iwh *)`

The `permissions.deny` list SHALL include:
- `Bash(lexictl *)`

#### Scenario: Generate settings.json from scratch
- **WHEN** `_generate_settings_json()` is called and no `.claude/settings.json` exists
- **THEN** the file SHALL be created with the permissions block and the `.claude/` directory SHALL be created if needed

#### Scenario: Merge with existing settings.json
- **WHEN** `_generate_settings_json()` is called and `.claude/settings.json` already exists with user-added allow entries
- **THEN** the Lexibrary entries SHALL be added to the existing `allow` and `deny` lists without removing any user entries
- **AND** the resulting lists SHALL be sorted and deduplicated

#### Scenario: Idempotent generation
- **WHEN** `_generate_settings_json()` is called twice
- **THEN** the resulting file SHALL be identical both times (no duplicate entries)

#### Scenario: Preserves non-permission keys
- **WHEN** `_generate_settings_json()` is called and existing settings.json contains keys other than `permissions` (e.g., `mcpServers`)
- **THEN** those keys SHALL be preserved unchanged

### Requirement: Generate Claude hook scripts
The system SHALL provide `_generate_hook_scripts(project_root: Path) -> list[Path]` in `src/lexibrary/init/rules/claude.py` that generates executable shell scripts in `.claude/hooks/`.

The following scripts SHALL be generated:
- `.claude/hooks/lexi-pre-edit.sh` — PreToolUse hook for auto-lookup
- `.claude/hooks/lexi-post-edit.sh` — PostToolUse hook for design file reminders

#### Scenario: Pre-edit hook script generated
- **WHEN** `_generate_hook_scripts()` is called
- **THEN** `.claude/hooks/lexi-pre-edit.sh` SHALL exist, be executable, and contain logic to extract `file_path` from stdin JSON and run `lexi lookup`

#### Scenario: Post-edit hook script generated
- **WHEN** `_generate_hook_scripts()` is called
- **THEN** `.claude/hooks/lexi-post-edit.sh` SHALL exist, be executable, and contain logic to emit a `systemMessage` reminder to update design files

#### Scenario: Post-edit hook excludes non-source paths
- **WHEN** the post-edit hook runs for a file path matching `*.lexibrary/*`, `*blueprints/*`, `*.claude/*`, or `*.cursor/*`
- **THEN** the hook SHALL exit 0 without emitting any message

#### Scenario: Hook scripts overwritten on regeneration
- **WHEN** `_generate_hook_scripts()` is called and hook scripts already exist
- **THEN** the scripts SHALL be overwritten with current content

### Requirement: Settings.json includes hooks configuration
The `_generate_settings_json()` function SHALL also include a `hooks` section in settings.json with:
- `PreToolUse` entry matching `Edit|Write` tools, running `lexi-pre-edit.sh` with 10s timeout
- `PostToolUse` entry matching `Edit|Write` tools, running `lexi-post-edit.sh` with 5s timeout

The hook command paths SHALL use `"$CLAUDE_PROJECT_DIR"/.claude/hooks/<script>` format.

#### Scenario: Hooks section in settings.json
- **WHEN** `_generate_settings_json()` generates settings.json
- **THEN** the file SHALL contain a `hooks` key with `PreToolUse` and `PostToolUse` arrays

#### Scenario: Merge hooks with existing hooks config
- **WHEN** settings.json already contains user-defined hooks
- **THEN** the Lexibrary hooks SHALL be appended to existing hook arrays without removing user hooks

### Requirement: Claude rules generation includes settings and hooks
The `generate_claude_rules()` function SHALL call `_generate_settings_json()` and `_generate_hook_scripts()` in addition to generating `CLAUDE.md` and command files. All generated paths SHALL be included in the returned list.

#### Scenario: Full Claude generation
- **WHEN** `generate_claude_rules()` is called
- **THEN** the returned path list SHALL include `.claude/settings.json`, `.claude/hooks/lexi-pre-edit.sh`, and `.claude/hooks/lexi-post-edit.sh` in addition to `CLAUDE.md` and command files

