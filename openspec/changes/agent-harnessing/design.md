## Context

Lexibrary generates agent rules and design files for AI coding environments. The current integration is limited to rule files — agents must manually approve CLI commands, have no automatic context injection, and lack tooling for common operations. Operators have no CI validation mode, no auto-fix, and a disconnected init→update workflow. The plan (`plans/agent-harnessing-plan.md`) documents 6 phases of improvements.

The existing codebase has:
- `src/lexibrary/init/rules/` — generators for Claude, Cursor, Codex environments
- `src/lexibrary/cli/` — `lexi` (agent) and `lexictl` (operator) apps
- `src/lexibrary/hooks/` — post-commit hook installer
- `src/lexibrary/validator/` — validation checks and reporting
- `src/lexibrary/archivist/pipeline.py` — design file generation pipeline

## Goals / Non-Goals

**Goals:**
- Zero-friction Claude Code agent experience (pre-approved commands, auto-context hooks)
- Operator workflow improvements (dry-run, CI validation, auto-fix, init→update flow)
- Agent tooling for design file management and Stack lifecycle
- Broader environment support (Cursor glob rules, generic fallback)

**Non-Goals:**
- MCP server for lexi commands (backlog L1)
- IDE workspace settings generation (backlog L3)
- `lexictl metrics` dashboard (backlog L6)
- Hook/sweep coordination (backlog M5)
- Windows hook support (backlog M8)
- Post-merge and post-checkout git hooks (backlog)

## Decisions

### D1: Claude settings.json merge strategy — Additive-only merge

Generate `.claude/settings.json` with `permissions.allow` and `permissions.deny` lists. When file already exists, merge by adding our entries to existing sets (deduplicating). Never remove user-added entries. This respects user customizations while ensuring Lexibrary commands work.

**Alternative considered:** Overwrite entire file. Rejected because it would destroy user customizations.

### D2: Hook scripts as separate .sh files, config in settings.json

Claude Code hooks are configured in `settings.json` under a `hooks` key, with actual logic in separate shell scripts under `.claude/hooks/`. This keeps settings.json clean and hook logic editable/debuggable.

**Alternative considered:** Inline command strings in settings.json. Rejected because multi-line shell logic is hard to maintain in JSON strings.

### D3: PreToolUse hook reads stdin JSON for file path

The `lexi-pre-edit.sh` script reads the tool input JSON from stdin to extract `file_path`, runs `lexi lookup`, and outputs `additionalContext` as JSON on stdout. Exit code 0 allows the operation.

### D4: Dry-run has two levels — detection-only (default) and full (with LLM)

Default `--dry-run` only runs change detection (fast, free). `--dry-run --full` does everything including LLM calls but skips file writes. This gives operators a fast preview by default while allowing prompt testing when needed.

**Alternative considered:** Single dry-run mode that always calls LLM. Rejected because it incurs cost for simple "what would change?" queries.

### D5: Validate --ci exit codes follow existing convention

The existing `exit_code()` returns 0/1/2. For CI mode, add compact single-line output and use the same exit codes: 0=clean, 1=errors, 2=warnings-only. This avoids a breaking change.

### D6: Auto-fix uses a registry pattern

`validator/fixes.py` maps check names to fixer functions. Only auto-fixable checks get fixers (hash_freshness, orphan_artifacts, aindex_coverage). Non-fixable checks are reported as `[SKIP]`. This is extensible — new fixers can be registered without changing the CLI.

### D7: `lexi design update` scaffolds without LLM

The design helper creates a template-based scaffold (no LLM call) or displays the existing design file with instructions. This is fast and free, suitable for agent workflows where the agent itself will fill in details.

### D8: Pre-commit hook depends on `lexictl validate --ci`

The pre-commit hook runs `lexictl validate --ci --severity error`. This creates a dependency: Phase 4 (pre-commit) must come after Phase 2.3 (--ci flag). The hook uses the `# lexibrary:pre-commit` marker pattern matching the existing post-commit hook.

### D9: Generic rules as single LEXIBRARY_RULES.md

For unsupported environments, generate a single `LEXIBRARY_RULES.md` at project root with core rules and skills embedded. Any agent can be pointed to this file. Registered as `"generic"` in the environment registry.

### D10: Init wizard extends with two new steps (hooks + auto-update)

Add `install_hooks: bool` to `WizardAnswers`. Add a step after environment selection offering hook installation, and a final prompt offering to run `lexictl update`. Auto-update defaults to `False` (expensive).

### D11: Stack CLI gets lifecycle subcommands wrapping existing mutations

The `mark_outdated` and `mark_duplicate` mutation functions already exist in `stack/mutations.py`. Add `lexi stack mark-outdated` and `lexi stack duplicate` CLI subcommands as thin wrappers.

## Risks / Trade-offs

- **[PreToolUse hook latency]** → `lexi lookup` runs on every Edit/Write. Mitigated by 10s timeout; lookup is fast (file path resolution + read).
- **[PostToolUse reminder noise]** → Agent gets reminded after every source file edit. Mitigated by excluding `.lexibrary/`, `blueprints/`, `.claude/`, `.cursor/` paths.
- **[Settings.json drift]** → User may remove our entries, then re-running init adds them back. Mitigated by additive merge — we never remove, only add.
- **[Dry-run accuracy]** → Detection-only dry-run predicts LLM calls but doesn't confirm LLM success. Acceptable — it's a preview, not a guarantee.
- **[Auto-fix safety]** → Orphan artifact deletion could remove intentionally orphaned files. Mitigated by only deleting confirmed orphans (design files whose `source_path` doesn't exist).
