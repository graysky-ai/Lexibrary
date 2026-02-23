# Lexibrary Memory

## Tooling
- Package manager: `uv` (not pip/poetry)
- Test runner: `uv run pytest`
- Lint/format: `uv run ruff`
- Type check: `uv run mypy src/` (strict)

## Workflow: OpenSpec + Beads integration
- Skills live in `.claude/skills/<name>/SKILL.md` (project-local)
- Slash commands live in `.claude/commands/opsx/<name>.md`
- After tasks.md is created by OpenSpec → run `/opsx:sync-beads` (automatic)
- Beads are source of truth for progress; tasks.md is reference only
- See `.claude/skills/openspec-sync-beads/SKILL.md` for full bead-creation logic

## Key paths
- OpenSpec changes: `openspec/changes/<name>/`
- Phase plans (read-only): `plans/`
- BAML prompts: `baml_src/`
