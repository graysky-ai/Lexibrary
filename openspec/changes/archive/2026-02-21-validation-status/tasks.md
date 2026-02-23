## 1. Report Models

- [x] 1.1 Create `src/lexibrary/validator/__init__.py` with `from __future__ import annotations` and re-exports for `validate_library`, `ValidationReport`, `ValidationIssue`
- [x] 1.2 Create `src/lexibrary/validator/report.py` with `ValidationIssue`, `ValidationSummary`, and `ValidationReport` dataclasses — include `has_errors()`, `has_warnings()`, `exit_code()`, `to_dict()`, and `render(console)` methods
- [x] 1.3 Write unit tests for `ValidationReport` — exit codes (0/1/2), `has_errors()`, `has_warnings()`, `to_dict()` serialization, empty report handling

## 2. Error-Severity Checks

- [x] 2.1 Implement `check_wikilink_resolution` in `src/lexibrary/validator/checks.py` — parse design files and Stack posts for wikilinks, use `WikilinkResolver` to verify, return errors with suggestions for unresolved links
- [x] 2.2 Implement `check_file_existence` — verify `source_path` in design files, `refs.files` and `refs.designs` in Stack posts all point to existing files
- [x] 2.3 Implement `check_concept_frontmatter` — validate all concept files have mandatory `title`, `aliases`, `tags`, `status` fields
- [x] 2.4 Write unit tests for error-severity checks — valid cases return empty, broken wikilinks produce errors with suggestions, missing files produce errors, invalid frontmatter produces errors

## 3. Warning-Severity Checks

- [x] 3.1 Implement `check_hash_freshness` — parse design file metadata (footer-only), compare `source_hash` against current SHA-256, return warnings for mismatches
- [x] 3.2 Implement `check_token_budgets` — count tokens using approximate tokenizer, compare against `TokenBudgetConfig` values, return warnings for over-budget artifacts
- [x] 3.3 Implement `check_orphan_concepts` — scan all artifacts for wikilink references, identify concepts with zero inbound references
- [x] 3.4 Implement `check_deprecated_concept_usage` — find deprecated concepts referenced by active artifacts, include `superseded_by` in suggestion
- [x] 3.5 Write unit tests for warning-severity checks — fresh hashes pass, stale hashes warn, within-budget passes, over-budget warns, referenced concepts pass, orphans warn, deprecated usage warns with superseded_by

## 4. Info-Severity Checks

- [x] 4.1 Implement `check_forward_dependencies` — parse design file dependency sections, verify targets exist on disk
- [x] 4.2 Implement `check_stack_staleness` — for Stack posts with `refs.files`, check if any referenced file's design file has a stale `source_hash`
- [x] 4.3 Implement `check_aindex_coverage` — walk `scope_root` directory tree, check for corresponding `.aindex` files in `.lexibrary/`
- [x] 4.4 Write unit tests for info-severity checks — existing deps pass, missing deps produce info, unchanged stack refs pass, changed refs produce info, indexed dirs pass, unindexed dirs produce info

## 5. Validation Orchestrator

- [x] 5.1 Implement `validate_library()` in `src/lexibrary/validator/__init__.py` — run all checks, aggregate into `ValidationReport`, support `severity_filter` and `check_filter` parameters
- [x] 5.2 Write integration tests with `tmp_path` fixtures — healthy project (no issues), mixed issues (errors + warnings + info), empty library (graceful handling), severity filter, check filter

## 6. CLI: `lexi validate` Command

- [x] 6.1 Replace the `validate` stub in `cli.py` with full implementation — run `validate_library()`, render with Rich, handle `--severity`, `--check`, `--json` flags, exit with 0/1/2
- [x] 6.2 Write CLI tests for `lexi validate` — clean exit 0, errors exit 1, warnings-only exit 2, `--json` produces valid JSON, `--severity` filters correctly, `--check` runs single check, invalid check name shows available checks

## 7. CLI: `lexi status` Command

- [x] 7.1 Replace the `status` stub in `cli.py` with full implementation — collect artifact counts, run lightweight validation (errors + warnings only), compute last update timestamp, render dashboard with Rich
- [x] 7.2 Implement `--quiet` flag — single-line output: "lexi: library healthy" or "lexi: N errors, M warnings — run `lexi validate`"
- [x] 7.3 Write CLI tests for `lexi status` — output format, quiet mode healthy, quiet mode with warnings, exit codes match validate scheme

## 8. Lookup Convention Inheritance

- [x] 8.1 Enhance `lexi lookup` in `cli.py` — after printing design file, walk parent `.aindex` files from file's directory to `scope_root`, collect `local_conventions`, append `## Applicable Conventions` section grouped by source directory
- [x] 8.2 Write CLI tests for lookup conventions — conventions from multiple parents shown in order, no conventions means no extra section, missing `.aindex` files silently skipped, walk stops at scope_root

## 9. Blueprints Update

- [x] 9.1 Update `blueprints/START_HERE.md` — add `validator` to Package Map and Navigation by Intent
- [x] 9.2 Create or update `blueprints/src/lexibrary/validator/` design files for the new module
