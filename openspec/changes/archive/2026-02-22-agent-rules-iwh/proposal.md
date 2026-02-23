## Why

Phase 8c completes the agent integration layer. Currently, agents have no inter-agent signalling (the project-wide HANDOFF.md is static and noisy) and no environment-specific rules telling them how to use the Lexibrary library. Without these, agents must be manually instructed each session — defeating the purpose of a self-documenting codebase. IWH provides ephemeral, directory-scoped signals that replace HANDOFF.md, and auto-generated agent rules make library usage automatic across Claude Code, Cursor, and Codex environments.

## What Changes

- **New `iwh/` module** — Pydantic model, parser, serializer, reader (with consume-on-read), writer, and gitignore integration for `.iwh` files
- **New `init/rules/` module** — Agent environment rule generators for Claude Code (CLAUDE.md + `.claude/commands/`), Cursor (`.cursor/rules/` + `.cursor/skills/`), and Codex (AGENTS.md)
- **Marker utilities** — `<!-- lexibrary:start/end -->` section management for appending/updating rule sections in existing files
- **`iwh_path()` helper** — Path computation for `.iwh` files in the `.lexibrary/` mirror tree
- **`lexictl setup --update` implementation** — Replace the stub with real rule generation, reading `agent_environment` from persisted config
- **HANDOFF.md removal** — Remove `HANDOFF_PLACEHOLDER`, scaffolder file creation, config `handoff_tokens`, and ignore pattern entries (**BREAKING** for projects with existing HANDOFF.md references)
- **Gitignore integration** — `ensure_iwh_gitignored()` called from scaffolder and rule generation to add `**/.iwh` pattern

## Capabilities

### New Capabilities
- `iwh-module`: I Was Here ephemeral inter-agent signalling — model, parse, serialize, read/consume, write `.iwh` files
- `agent-rule-templates`: Generate environment-specific rule files (CLAUDE.md, .cursor/rules, AGENTS.md) with skills and commands
- `rule-markers`: Section marker utilities for safe append/replace in existing markdown files
- `setup-update-command`: `lexictl setup --update` CLI implementation for refreshing agent rules

### Modified Capabilities
- `project-scaffolding`: Remove HANDOFF.md creation; update START_HERE placeholder to reference IWH; wire `ensure_iwh_gitignored()` into skeleton creation
- `config-system`: Remove `handoff_tokens` from `TokenBudgetConfig`
- `utilities`: Add `iwh_path()` helper to `utils/paths.py`
- `ignore-system`: Remove `.lexibrary/HANDOFF.md` from default additional patterns

## Impact

- **New files**: ~13 source files (`iwh/` module + `init/rules/` module), ~18 test files
- **Modified files**: `init/scaffolder.py`, `config/schema.py`, `config/defaults.py`, `utils/paths.py`, `cli/lexictl_app.py`, ignore defaults
- **Dependencies**: Phase 8a (CLI split — `lexictl` must exist) and Phase 8b (init wizard — `agent_environment` persisted in config)
- **No new package dependencies** — uses existing PyYAML, Pydantic 2, pathspec, rich
- **Breaking**: Projects referencing HANDOFF.md in custom tooling will need to migrate to IWH. `handoff_tokens` config key silently ignored via Pydantic `extra="ignore"`
