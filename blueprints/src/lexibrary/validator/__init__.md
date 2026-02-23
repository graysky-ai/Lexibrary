# validator

**Summary:** Library health checks and validation reporting -- orchestrates 13 individual checks grouped by severity (error, warning, info), aggregates results into a `ValidationReport`, and provides filtering by severity and check name. Includes three link-graph checks (`bidirectional_deps`, `dangling_links`, `orphan_artifacts`) that degrade gracefully when `index.db` is absent.

## Re-exports

`validate_library`, `ValidationReport`, `ValidationIssue`, `ValidationSummary`, `AVAILABLE_CHECKS`

## Interface

| Name | Key Fields / Signature | Purpose |
| --- | --- | --- |
| `AVAILABLE_CHECKS` | `dict[str, tuple[CheckFn, Severity]]` | Registry mapping check name to (function, default severity) |
| `validate_library` | `(project_root, lexibrary_dir, *, severity_filter?, check_filter?) -> ValidationReport` | Run all (or filtered) checks and return aggregated report |

## Check Registry

| Check Name | Severity | Function |
| --- | --- | --- |
| `wikilink_resolution` | error | `check_wikilink_resolution` |
| `file_existence` | error | `check_file_existence` |
| `concept_frontmatter` | error | `check_concept_frontmatter` |
| `hash_freshness` | warning | `check_hash_freshness` |
| `token_budgets` | warning | `check_token_budgets` |
| `orphan_concepts` | warning | `check_orphan_concepts` |
| `deprecated_concept_usage` | warning | `check_deprecated_concept_usage` |
| `forward_dependencies` | info | `check_forward_dependencies` |
| `stack_staleness` | info | `check_stack_staleness` |
| `aindex_coverage` | info | `check_aindex_coverage` |
| `bidirectional_deps` | info | `check_bidirectional_deps` |
| `dangling_links` | info | `check_dangling_links` |
| `orphan_artifacts` | info | `check_orphan_artifacts` |

## Orchestration Logic

1. Validate `severity_filter` and `check_filter` parameters (raise `ValueError` on invalid input)
2. Build `checks_to_run` dict -- filtered by `check_filter` (single check) and/or `severity_filter` (threshold-based: only checks at or above threshold severity)
3. Run each selected check, catching exceptions to prevent individual failures from aborting the run
4. Aggregate all `ValidationIssue` objects into a single `ValidationReport`

## Dependencies

- `lexibrarian.validator.checks` -- all 13 check functions
- `lexibrarian.validator.report` -- `ValidationIssue`, `ValidationReport`, `ValidationSummary`, `Severity`

## Dependents

- `lexibrarian.cli` -- `lexi validate` and `lexi status` commands
