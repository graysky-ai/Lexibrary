## Why

The `lexi`/`lexictl` command divide is based on agent-safety, but the current assignment has operational mismatches: `lexi index` is a maintenance/generation command that agents rarely need during a coding session, while `lexictl validate` and `lexictl status` are read-only inspection commands that agents *should* be using to check their work and orient themselves. The `agent-rule-templates` spec already tells agents to "run `lexi status`" in the orient skill, and the `library-status` spec already references `lexi status` in 6 of 7 requirements — but the implementation puts both on `lexictl`. This change corrects the divide so that agents have all read/inspect commands and infrastructure generation is fully automated.

Follows directly from the `agent-navigation` change which added `lexi help` — that help text must be updated to reflect the rebalanced commands.

## What Changes

- **BREAKING**: Remove `lexi index` command; add `lexictl index` command with identical interface
- Register `lexi validate` as an agent-facing entry point for library validation (mirrors `lexictl validate` with identical flags)
- Register `lexi status` as an agent-facing entry point for library health (mirrors `lexictl status` with identical flags)
- Integrate `.aindex` regeneration into the post-commit hook flow (alongside `lexictl update --changed-only`)
- Integrate `.aindex` regeneration into `lexictl sweep` (one-shot and watch modes)
- Update `lexi help` content: remove "Indexing & Maintenance" section, add "Inspection & Health" section with `validate`/`status`, keep `describe` under a suitable heading, replace "Index a new directory" workflow
- Update agent rule templates (`base.py`, Claude/Cursor/Codex generators) to reference `lexi validate`, `lexi status`, and remove `lexi index`
- Update `lexi --help` listing to include `validate`, `status`, `help` and exclude `index`

## Capabilities

### New Capabilities
- `automated-indexing`: Automatic `.aindex` regeneration triggered by the post-commit hook and periodic sweep, eliminating the need for manual `lexi index` invocations

### Modified Capabilities
- `cli-commands`: Move `index` from `lexi` to `lexictl`; register `validate` and `status` on `lexi`; update `lexi --help` listing and `lexi help` content to match
- `agent-rule-templates`: Add `lexi validate` and `lexi status` to recommended agent commands; remove `lexi index` references; update orient skill

## Impact

- **Files modified**: `src/lexibrary/cli/lexi_app.py`, `src/lexibrary/cli/lexictl_app.py`, `src/lexibrary/init/rules/base.py`, `src/lexibrary/init/rules/claude.py`, `src/lexibrary/init/rules/cursor.py`, `src/lexibrary/init/rules/codex.py`, `src/lexibrary/hooks/post_commit.py`, `src/lexibrary/daemon/service.py`
- **Blueprints updated**: design files for all modified source files
- **Tests updated**: CLI tests for command registration, help text content, agent rule output
- **Dependencies**: None — uses existing infrastructure (validation, status, indexer, hooks)
- **Phase**: Current (CLI layer + hook/sweep integration, no new deps)
- **Breaking**: Scripts or agents calling `lexi index` must switch to `lexictl index` or rely on automated indexing
- **Depends on**: `agent-navigation` change (provides `lexi help` command that this change modifies)
