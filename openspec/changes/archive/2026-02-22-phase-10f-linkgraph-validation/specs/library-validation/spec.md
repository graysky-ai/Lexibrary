## MODIFIED Requirements

### Requirement: validate_library orchestrates all checks
The `validate_library` function SHALL accept `project_root` and `lexibrary_dir` Path arguments and run all 13 check functions (the original 10 plus 3 new link-graph checks), aggregating results into a single `ValidationReport`. It SHALL support optional `severity_filter` (minimum severity to include) and `check_filter` (run only a named check) parameters.

#### Scenario: Full validation with no filters
- **WHEN** calling `validate_library(project_root, lexibrary_dir)` with no filters
- **THEN** all 13 checks run and results are combined into one `ValidationReport`

#### Scenario: Severity filter excludes lower severities
- **WHEN** calling `validate_library` with `severity_filter="warning"`
- **THEN** only error and warning issues appear in the report (info excluded, including link-graph info checks)

#### Scenario: Check filter runs single check
- **WHEN** calling `validate_library` with `check_filter="bidirectional_deps"`
- **THEN** only `check_bidirectional_deps` runs and its results appear in the report

#### Scenario: Link-graph checks gracefully skipped when index missing
- **WHEN** calling `validate_library` with no filters and `index.db` does not exist
- **THEN** all 13 checks run; the 3 link-graph checks return empty lists and the remaining 10 file-based checks produce their normal results

## ADDED Requirements

### Requirement: AVAILABLE_CHECKS includes link-graph checks
The `AVAILABLE_CHECKS` registry SHALL include entries for `"bidirectional_deps"`, `"dangling_links"`, and `"orphan_artifacts"`, each with default severity `"info"`. These entries SHALL map to check functions that accept the standard `(project_root, lexibrary_dir) -> list[ValidationIssue]` signature.

#### Scenario: New checks are registered
- **WHEN** importing `AVAILABLE_CHECKS` from `lexibrarian.validator`
- **THEN** `"bidirectional_deps"`, `"dangling_links"`, and `"orphan_artifacts"` are present as keys with their check functions and `"info"` default severity

#### Scenario: New checks appear in help output
- **WHEN** running `lexictl validate --check nonexistent`
- **THEN** the error message listing available checks includes `bidirectional_deps`, `dangling_links`, and `orphan_artifacts`
