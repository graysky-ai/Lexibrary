# library-validation Specification

## Purpose
TBD - created by archiving change validation-status. Update Purpose after archive.
## Requirements
### Requirement: ValidationIssue model captures check results
The `ValidationIssue` dataclass SHALL have fields: `severity` (literal "error", "warning", or "info"), `check` (string identifying the check name), `message` (human/agent-readable description), `artifact` (path to the artifact with the issue), and `suggestion` (actionable fix recommendation).

#### Scenario: ValidationIssue has all required fields
- **WHEN** creating a `ValidationIssue` with severity="error", check="wikilink_resolution", message="[[AuthFlow]] does not resolve", artifact="src/api/auth.py.md", suggestion="Did you mean [[Authentication]]?"
- **THEN** all fields are accessible and the issue is usable in a `ValidationReport`

### Requirement: ValidationReport aggregates issues with summary
The `ValidationReport` SHALL contain a list of `ValidationIssue` objects and a `ValidationSummary` with counts by severity. It SHALL provide `has_errors()`, `has_warnings()`, and `exit_code()` methods. `exit_code()` SHALL return 0 when no errors or warnings exist, 1 when errors exist, and 2 when warnings exist but no errors.

#### Scenario: Report with errors returns exit code 1
- **WHEN** a `ValidationReport` contains at least one issue with severity "error"
- **THEN** `has_errors()` returns True and `exit_code()` returns 1

#### Scenario: Report with only warnings returns exit code 2
- **WHEN** a `ValidationReport` contains warnings but no errors
- **THEN** `has_errors()` returns False, `has_warnings()` returns True, and `exit_code()` returns 2

#### Scenario: Report with only info issues returns exit code 0
- **WHEN** a `ValidationReport` contains only info-severity issues
- **THEN** `has_errors()` returns False, `has_warnings()` returns False, and `exit_code()` returns 0

#### Scenario: Empty report returns exit code 0
- **WHEN** a `ValidationReport` contains no issues
- **THEN** `exit_code()` returns 0

### Requirement: ValidationReport renders with Rich
The `ValidationReport` SHALL provide a `render(console)` method that outputs issues grouped by severity (errors first, then warnings, then info) with appropriate symbols (cross for errors, warning triangle for warnings, info circle for info). Each issue SHALL display its message and suggestion.

#### Scenario: Rich rendering shows grouped issues
- **WHEN** calling `render()` on a report with 1 error, 2 warnings, and 1 info issue
- **THEN** output shows "Errors (1)" section, "Warnings (2)" section, "Info (1)" section, and a summary line

### Requirement: ValidationReport renders as JSON
The `ValidationReport` SHALL provide a `to_dict()` method that returns a JSON-serializable dictionary containing all issues and summary counts.

#### Scenario: JSON output is valid and complete
- **WHEN** calling `to_dict()` on a report with mixed issues
- **THEN** the result is a dictionary with "issues" (list of dicts) and "summary" (dict with error_count, warning_count, info_count)

### Requirement: check_wikilink_resolution detects broken wikilinks
The `check_wikilink_resolution` function SHALL parse all design files and Stack posts, collect all wikilink references, and use `WikilinkResolver` to verify each resolves. Unresolved links SHALL produce an error-severity issue with the closest match as a suggestion.

#### Scenario: All wikilinks resolve
- **WHEN** all `[[ConceptName]]` references in design files and Stack posts resolve to existing concepts or Stack posts
- **THEN** no issues are returned

#### Scenario: Broken wikilink produces error with suggestion
- **WHEN** a design file contains `[[AuthFlow]]` but no concept named "AuthFlow" exists and the closest match is "Authentication"
- **THEN** an error issue is returned with check="wikilink_resolution" and suggestion containing "Authentication"

### Requirement: check_file_existence detects missing source files
The `check_file_existence` function SHALL verify that all `source_path` values in design files, all `refs.files` entries in Stack posts, and all `refs.designs` entries in Stack posts point to files that exist. Missing files SHALL produce error-severity issues.

#### Scenario: All referenced files exist
- **WHEN** all source files referenced by design files and Stack posts exist on disk
- **THEN** no issues are returned

#### Scenario: Missing source file produces error
- **WHEN** a design file references `src/old_module.py` which no longer exists
- **THEN** an error issue is returned with check="file_existence" and a suggestion to remove the design file or restore the source

#### Scenario: Missing Stack ref file produces error
- **WHEN** a Stack post's `refs.files` lists a file that does not exist
- **THEN** an error issue is returned with check="file_existence"

### Requirement: check_concept_frontmatter validates mandatory fields
The `check_concept_frontmatter` function SHALL parse all concept files and verify that `title`, `aliases`, `tags`, and `status` fields are present and valid. Invalid or missing fields SHALL produce error-severity issues.

#### Scenario: Valid concept frontmatter passes
- **WHEN** a concept file has valid `title`, `aliases` (min 1), `tags` (min 1), and `status` (active/deprecated/draft)
- **THEN** no issues are returned

#### Scenario: Missing frontmatter field produces error
- **WHEN** a concept file is missing the `title` field
- **THEN** an error issue is returned with check="concept_frontmatter"

### Requirement: check_hash_freshness detects stale design files
The `check_hash_freshness` function SHALL parse design file metadata (footer only) and compare `source_hash` against the current SHA-256 of the source file. Mismatches SHALL produce warning-severity issues.

#### Scenario: Fresh design file passes
- **WHEN** a design file's `source_hash` matches the current source file hash
- **THEN** no issues are returned

#### Scenario: Stale design file produces warning
- **WHEN** a design file's `source_hash` differs from the current source file hash
- **THEN** a warning issue is returned with check="hash_freshness" and suggestion to run `lexi update`

### Requirement: check_token_budgets validates artifact sizes
The `check_token_budgets` function SHALL count tokens in each artifact using the approximate tokenizer and compare against configured budgets from `TokenBudgetConfig`. Artifacts exceeding their budget SHALL produce warning-severity issues with actual vs target counts.

#### Scenario: Artifact within budget passes
- **WHEN** a design file has 300 tokens and the budget is 400
- **THEN** no issues are returned

#### Scenario: Artifact over budget produces warning
- **WHEN** a design file has 620 tokens and the budget is 400
- **THEN** a warning issue is returned with check="token_budget" showing actual=620 and target=400

### Requirement: check_orphan_concepts detects unreferenced concepts
The `check_orphan_concepts` function SHALL scan all design files, Stack posts, and concept files for wikilink references, then identify concepts with zero inbound references. Orphan concepts SHALL produce warning-severity issues.

#### Scenario: Referenced concept passes
- **WHEN** a concept is referenced by at least one design file, Stack post, or other concept
- **THEN** no issue is returned for that concept

#### Scenario: Orphan concept produces warning
- **WHEN** a concept has zero inbound references from any artifact
- **THEN** a warning issue is returned with check="orphan_concept" and suggestion to deprecate or link

### Requirement: check_deprecated_concept_usage detects active references to deprecated concepts
The `check_deprecated_concept_usage` function SHALL find concepts with `status: deprecated` and check if any design files or Stack posts still reference them. Active references to deprecated concepts SHALL produce warning-severity issues with the `superseded_by` value as suggestion.

#### Scenario: No references to deprecated concept
- **WHEN** a deprecated concept is not referenced by any active artifact
- **THEN** no issues are returned

#### Scenario: Active reference to deprecated concept produces warning
- **WHEN** a design file references `[[OldPattern]]` which has `status: deprecated` and `superseded_by: NewPattern`
- **THEN** a warning issue is returned with check="deprecated_concept_usage" and suggestion mentioning "NewPattern"

### Requirement: check_forward_dependencies verifies dependency targets exist
The `check_forward_dependencies` function SHALL parse design files and verify that each entry in the `## Dependencies` section points to a file that exists. Missing targets SHALL produce info-severity issues.

#### Scenario: All dependencies exist
- **WHEN** all files listed in design file dependency sections exist on disk
- **THEN** no issues are returned

#### Scenario: Missing dependency target produces info
- **WHEN** a design file lists a dependency on `src/utils/helper.py` which does not exist
- **THEN** an info issue is returned with check="forward_dependencies"

### Requirement: check_stack_staleness flags potentially outdated Stack posts
The `check_stack_staleness` function SHALL check Stack posts with `refs.files` entries by looking up whether any referenced file's design file has a stale `source_hash`. Potentially outdated posts SHALL produce info-severity issues.

#### Scenario: Stack post references unchanged files
- **WHEN** all files referenced by a Stack post have current (non-stale) design files
- **THEN** no issues are returned

#### Scenario: Stack post references changed files produces info
- **WHEN** a Stack post references `src/api/events.py` whose design file has a stale `source_hash`
- **THEN** an info issue is returned with check="stack_staleness" and suggestion to verify the solution still applies

### Requirement: check_aindex_coverage finds unindexed directories
The `check_aindex_coverage` function SHALL walk the `scope_root` directory tree and check that each directory has a corresponding `.aindex` file in `.lexibrary/`. Missing `.aindex` files SHALL produce info-severity issues.

#### Scenario: All directories indexed
- **WHEN** every directory within `scope_root` has a corresponding `.aindex` file
- **THEN** no issues are returned

#### Scenario: Unindexed directory produces info
- **WHEN** a directory within `scope_root` lacks a corresponding `.aindex` file
- **THEN** an info issue is returned with check="aindex_coverage" and suggestion "directory not indexed"

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

### Requirement: AVAILABLE_CHECKS includes link-graph checks
The `AVAILABLE_CHECKS` registry SHALL include entries for `"bidirectional_deps"`, `"dangling_links"`, and `"orphan_artifacts"`, each with default severity `"info"`. These entries SHALL map to check functions that accept the standard `(project_root, lexibrary_dir) -> list[ValidationIssue]` signature.

#### Scenario: New checks are registered
- **WHEN** importing `AVAILABLE_CHECKS` from `lexibrarian.validator`
- **THEN** `"bidirectional_deps"`, `"dangling_links"`, and `"orphan_artifacts"` are present as keys with their check functions and `"info"` default severity

#### Scenario: New checks appear in help output
- **WHEN** running `lexictl validate --check nonexistent`
- **THEN** the error message listing available checks includes `bidirectional_deps`, `dangling_links`, and `orphan_artifacts`

