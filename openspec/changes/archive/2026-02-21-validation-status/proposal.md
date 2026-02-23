## Why

Lexibrary has no way to detect library inconsistencies (broken wikilinks, missing source files, stale design files) or give agents a quick health snapshot at session start. Phases 4–6 built the artifacts; Phase 7 builds the inspection tools that keep them honest. Without validation, library rot accumulates silently and agents work with outdated or broken references.

## What Changes

- New `validator/` module with 10 check functions across three severity tiers (error, warning, info)
- New `ValidationReport` model with Rich rendering and structured JSON output
- `lexi validate` command replaces its current stub — runs checks, reports issues, exits with 0/1/2
- `lexi status` command replaces its current stub — compact health dashboard, `--quiet` mode for hooks
- `lexi lookup` enhanced with convention inheritance — walks parent `.aindex` files to surface scoped Local Conventions
- All commands are read-only; no file modifications

## Capabilities

### New Capabilities
- `library-validation`: Validation engine with 10 named checks across error/warning/info severity tiers, producing a `ValidationReport` with Rich and JSON rendering
- `library-status`: Compact health dashboard aggregating artifact counts, staleness, and issue summaries with `--quiet` mode for agent hooks
- `lookup-conventions`: Convention inheritance for `lexi lookup` — walks parent `.aindex` files up to `scope_root` and appends applicable Local Conventions

### Modified Capabilities
- `cli-commands`: Adding `validate` (with `--severity`, `--check`, `--json` flags), `status` (with `--quiet` flag), and enhancing `lookup` with convention inheritance output

## Impact

- **New code:** `src/lexibrary/validator/` package (3 files: `__init__.py`, `checks.py`, `report.py`)
- **Modified code:** `src/lexibrary/cli.py` — replace `validate`/`status` stubs, enhance `lookup`
- **Dependencies on existing modules:** `artifacts.design_file_parser` (metadata + full parse), `artifacts.aindex_parser`, `wiki.resolver`, `stack.parser`, `config.loader`, `tokenizer.factory`, `artifacts.concept` (ConceptIndex)
- **No new external dependencies** — uses existing Rich, Pydantic, pathlib
- **Exit codes (CI-facing):** 0 = clean, 1 = errors, 2 = warnings only — must be reliable for pipeline gating
- **Blueprints:** `START_HERE.md` and `cli.md` design file need updates to reflect new `validator/` package
