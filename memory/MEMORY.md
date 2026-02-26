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

## Convention System Decisions (from `plans/conventions-artifact.md`)

- **Storage**: File-based in `.lexibrary/conventions/`, mirroring concepts structure. Separated from `.aindex` entirely.
- **Git**: All Lexibrary artifacts (including conventions) should be committed to version control.
- **Sign-off**: Config option `artifact_review` for auto (LLM-as-judge) vs manual (user review) sign-off. Extensible to all artifact types.
- **Display limit**: Default 5 conventions per `lexi lookup`, configurable via `conventions.lookup_display_limit`, warn if exceeded.
- **Conflicts**: Override by specificity (child scope wins) + validation warning for detected conflicts.
- **Pattern scopes**: Supported (glob patterns like `*_test.py`). Data model supports from day one, implementation may defer to v2.
- **Migration**: Not needed — changes are pre-launch.

## Key paths
- OpenSpec changes: `openspec/changes/<name>/`
- Phase plans (read-only): `plans/`
- BAML prompts: `baml_src/`
