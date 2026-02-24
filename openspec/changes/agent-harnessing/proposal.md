## Why

AI coding agents using Lexibrary face excessive friction: they must manually approve every CLI command, lack automatic design-context injection, and have no tooling for common operations like updating design files or previewing changes. Operators lack CI validation, auto-fix capabilities, and a smooth init-to-update workflow. This change addresses every open item from the agent harnessing analysis to make Lexibrary a seamless, zero-friction experience for both agents and operators.

## What Changes

- Generate `.claude/settings.json` with pre-approved `lexi` commands and hook definitions for automatic context injection before/after file edits
- Generate `.claude/hooks/` shell scripts for PreToolUse (auto-lookup) and PostToolUse (design-file reminders)
- Add 3 new Claude Code slash commands: `/lexi-lookup`, `/lexi-concepts`, `/lexi-stack`
- Add `--dry-run` flag to `lexictl update` for previewing changes without LLM calls or writes
- Add `--start-here` flag to `lexictl update` for standalone START_HERE.md regeneration
- Add `--ci` flag to `lexictl validate` with compact output and strict exit codes (0/1/2)
- Add `--fix` flag to `lexictl validate` with auto-fix framework for remediable issues
- Add `lexi design update <file>` command for agents to scaffold/display design files
- Add `lexi stack mark-outdated` and `lexi stack duplicate` lifecycle commands
- Add pre-commit validation hook alongside existing post-commit hook
- Add glob-scoped Cursor editing rules triggered on source file edits
- Add generic `LEXIBRARY_RULES.md` fallback for unsupported environments
- Add hook installation prompt and auto-update offer during `lexictl init` wizard
- **Backlog triage**: Track deferred items (MCP server, IDE workspace settings, metrics dashboard, hook/sweep coordination, Windows hooks, post-merge/checkout hooks)

## Capabilities

### New Capabilities
- `claude-agent-integration`: Generate `.claude/settings.json` (permissions + hooks config) and `.claude/hooks/` shell scripts for frictionless Claude Code agent experience
- `validate-autofix`: Auto-fix framework with per-check fixers for `--fix` flag (hash freshness, orphan artifacts, aindex coverage)
- `agent-design-helper`: `lexi design update <file>` command to scaffold or display design files for agent workflows
- `generic-agent-rules`: Generate `LEXIBRARY_RULES.md` fallback for environments without specific integration (Windsurf, Copilot, Aider, etc.)
- `pre-commit-validation`: Pre-commit git hook running `lexictl validate --ci` as a commit gate

### Modified Capabilities
- `agent-rule-templates`: Add 3 new skill content functions (lookup, concepts, stack) and Cursor glob-scoped editing rules
- `library-validation`: Add `--ci` mode with compact output and strict exit codes (0=clean, 1=errors, 2=internal failure)
- `archivist-pipeline`: Add `dry_run_project()` for change-detection-only preview and standalone START_HERE.md regeneration
- `git-hook-installation`: Extend to install pre-commit hook alongside post-commit; update `lexictl setup --hooks`
- `init-wizard`: Add hook installation prompt and optional auto-update offer after init
- `stack-mutations`: Add `mark-outdated` and `duplicate` lifecycle subcommands

## Impact

- **Files changed**: ~25 files across `src/lexibrary/` (init/rules, cli, archivist, validator, hooks)
- **New files**: 4 (validator/fixes.py, hooks/pre_commit.py, init/rules/generic.py, and test files)
- **CLI surface**: 7 new flags/commands on `lexi`/`lexictl`
- **Generated artifacts**: New `.claude/settings.json`, `.claude/hooks/*.sh`, `.cursor/rules/lexibrary-editing.mdc`, `LEXIBRARY_RULES.md`
- **Dependencies**: No new runtime dependencies required
- **Breaking changes**: None
