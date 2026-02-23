## Context

Phase 8c is the final piece of the agent integration layer. Phase 8a splits the CLI into `lexi` (agent-facing) and `lexictl` (maintenance), and Phase 8b implements the init wizard that persists `agent_environment` in config. Phase 8c builds on both to deliver:

1. **I Was Here (IWH)** — ephemeral, directory-scoped inter-agent signals replacing the project-wide HANDOFF.md
2. **Agent environment rules** — auto-generated rule files, skills, and commands for Claude Code, Cursor, and Codex
3. **HANDOFF.md cleanup** — removal of all HANDOFF.md scaffolding per D-053

The codebase already has well-established patterns for YAML frontmatter parsing (stack/parser.py), Pydantic 2 models, path computation helpers (utils/paths.py), and ignore system integration. Phase 8c follows these patterns consistently.

**Current state:** The `setup` command exists as a stub (`_stub("setup")`). HANDOFF.md is created by the scaffolder with a placeholder. `handoff_tokens` exists in `TokenBudgetConfig`. No IWH or rules infrastructure exists.

## Goals / Non-Goals

**Goals:**
- Implement a complete `iwh/` module (model, parser, serializer, reader with consume-on-read, writer, gitignore integration)
- Implement `init/rules/` module generating environment-specific agent rules for Claude Code, Cursor, and Codex
- Provide marker utilities for safe section insertion/replacement in existing files (CLAUDE.md, AGENTS.md)
- Add `iwh_path()` helper to `utils/paths.py`
- Replace `lexictl setup` stub with real rule generation reading from persisted config
- Remove all HANDOFF.md scaffolding (constant, file creation, config field, ignore pattern)
- Wire `ensure_iwh_gitignored()` into scaffolder and rule generation

**Non-Goals:**
- Automated pre-session or pre-edit hooks (instructions-based only in MVP — see 8c-4 decision)
- Subagent patterns or library maintenance subagent
- Multi-repo rule generation
- IWH configuration beyond `iwh.enabled` toggle (already in config from Phase 8b)
- Conflict resolution for same-directory `.iwh` race conditions (accepted limitation per Q-014)

## Decisions

### IWH module follows stack parser pattern
**Decision:** Mirror the `stack/parser.py` approach — `_FRONTMATTER_RE` regex, `yaml.safe_load`, Pydantic model construction.
**Why:** Consistency across the codebase. Developers familiar with stack parsing can immediately understand IWH parsing. Same error handling patterns (return None on failure).
**Alternative:** Dedicated YAML parser library — rejected as over-engineering for simple frontmatter.

### Consume-on-read deletes even corrupt files
**Decision:** `consume_iwh()` always deletes the `.iwh` file, even if parsing fails.
**Why:** IWH is advisory. A corrupt file blocking all subsequent agents is worse than losing a signal. The file is ephemeral — its purpose is transient notification, not durable state.
**Alternative:** Leave corrupt files for manual cleanup — rejected because IWH files are gitignored and invisible to most tooling.

### Marker-based section management for CLAUDE.md/AGENTS.md
**Decision:** Use `<!-- lexibrary:start -->` / `<!-- lexibrary:end -->` HTML comment markers to delimit Lexibrary's section in shared files.
**Why:** Users may have their own content in CLAUDE.md/AGENTS.md. Markers let us safely update our section without touching user content. HTML comments are invisible in rendered markdown.
**Alternative:** Separate file (e.g., `CLAUDE_LEXI.md`) — rejected because agents load CLAUDE.md automatically; a separate file requires manual inclusion.

### Cursor uses dedicated `.mdc` file, not marker-based append
**Decision:** Write `.cursor/rules/lexibrary.mdc` as a standalone file (overwritten on update) rather than appending to existing rules files.
**Why:** Cursor's MDC format uses YAML frontmatter with `alwaysApply: true`. It's a self-contained file in a directory Cursor scans. No user content to preserve.

### Skills content defined in `base.py`, placed by environment modules
**Decision:** Shared skill content (orient, search) is defined once in `base.py` and each environment module places it in the correct location/format.
**Why:** Avoids duplicating skill logic across environments. Single source of truth for what the skills do.

### Instructions-based hooks, not automated
**Decision:** No automated pre-session or pre-edit hooks in MVP. Rules instruct agents to perform these actions. The `/lexi-orient` skill provides a one-command session start.
**Why:** Claude Code, Cursor, and Codex lack reliable pre-session hook infrastructure. Instructions via rules files are universally supported.

### Rules instruct agents to never run `lexictl` commands
**Decision:** Agent rules explicitly state that agents must never invoke `lexictl` commands (init, update, validate, status). Only `lexi` commands are permitted.
**Why:** Enforces D-051/D-052 separation. Prevents agents from accidentally triggering expensive LLM calls or maintenance operations.

## Risks / Trade-offs

**[Risk] HANDOFF.md backward compatibility** → Projects with custom tooling referencing HANDOFF.md will break. **Mitigation:** Pydantic `extra="ignore"` silently handles stale `handoff_tokens` in config YAML. Document migration in release notes.

**[Risk] Same-directory `.iwh` race condition** → Two agents in the same directory may overwrite each other's signal. **Mitigation:** Accepted per Q-014. IWH is advisory. Document in docstrings. Agents in parallel workflows should coordinate through task systems (Beads).

**[Risk] Marker detection edge cases** → Users may accidentally place text between markers, or markers may get corrupted by editor formatting. **Mitigation:** Thorough test coverage for whitespace, trailing newlines, extra content between markers. `replace_lexibrary_section()` is robust to surrounding whitespace.

**[Risk] Agent environment detection fails** → Auto-detection may miss environments or false-positive. **Mitigation:** `lexictl setup` accepts explicit environment argument. Config persists the selection for future updates.

**[Risk] Rule content becomes stale** → As Lexibrary evolves, rules may reference commands that have changed. **Mitigation:** `lexictl setup --update` regenerates rules from current templates. Rule content lives in code (not config), so updates ship with new versions.

## Open Questions

- None — all Phase 8c questions (Q-014) have been resolved. The plan is comprehensive.
