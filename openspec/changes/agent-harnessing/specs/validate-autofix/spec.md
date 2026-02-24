## ADDED Requirements

### Requirement: FixResult model
The system SHALL define a `FixResult` dataclass in `src/lexibrary/validator/fixes.py` with fields: `check` (str), `path` (Path), `fixed` (bool), and `message` (str).

#### Scenario: FixResult represents successful fix
- **WHEN** creating `FixResult(check="hash_freshness", path=Path("src/foo.py"), fixed=True, message="re-generated design file")`
- **THEN** all fields SHALL be accessible

#### Scenario: FixResult represents skipped fix
- **WHEN** creating `FixResult(check="orphan_concepts", path=Path("concepts/old.md"), fixed=False, message="requires manual review")`
- **THEN** `fixed` SHALL be `False`

### Requirement: Fix hash freshness
The system SHALL provide `fix_hash_freshness(issue: ValidationIssue, project_root: Path, config: LexibraryConfig) -> FixResult` that re-generates the design file for a stale source file by calling the update pipeline for that file.

#### Scenario: Stale file re-generated
- **WHEN** `fix_hash_freshness()` is called for a file with mismatched source_hash
- **THEN** the design file SHALL be re-generated and a `FixResult` with `fixed=True` SHALL be returned

#### Scenario: Source file missing
- **WHEN** `fix_hash_freshness()` is called but the source file no longer exists
- **THEN** a `FixResult` with `fixed=False` SHALL be returned

### Requirement: Fix orphan artifacts
The system SHALL provide `fix_orphan_artifacts(issue: ValidationIssue, project_root: Path) -> FixResult` that deletes design files whose corresponding source file does not exist.

#### Scenario: Orphan deleted
- **WHEN** `fix_orphan_artifacts()` is called for a design file whose `source_path` does not exist
- **THEN** the design file SHALL be deleted and a `FixResult` with `fixed=True` SHALL be returned

#### Scenario: Source exists — not an orphan
- **WHEN** `fix_orphan_artifacts()` is called but the source file actually exists
- **THEN** the design file SHALL NOT be deleted and `fixed=False` SHALL be returned

### Requirement: Fix aindex coverage
The system SHALL provide `fix_aindex_coverage(issue: ValidationIssue, project_root: Path) -> FixResult` that generates missing `.aindex` files for uncovered directories by running the index generator for that directory.

#### Scenario: Missing aindex generated
- **WHEN** `fix_aindex_coverage()` is called for a directory without an `.aindex` file
- **THEN** an `.aindex` file SHALL be generated and `fixed=True` SHALL be returned

### Requirement: FIXERS registry
The system SHALL provide a `FIXERS: dict[str, Callable]` registry mapping check names to fixer functions. Only auto-fixable checks SHALL have entries: `hash_freshness`, `orphan_artifacts`, `aindex_coverage`.

#### Scenario: Registry contains fixable checks
- **WHEN** importing `FIXERS` from `lexibrary.validator.fixes`
- **THEN** it SHALL contain keys `"hash_freshness"`, `"orphan_artifacts"`, and `"aindex_coverage"`

#### Scenario: Non-fixable checks absent from registry
- **WHEN** checking `FIXERS` for `"orphan_concepts"` or `"token_budgets"`
- **THEN** those keys SHALL NOT be present

### Requirement: CLI --fix flag orchestration
The `_run_validate()` function in `src/lexibrary/cli/_shared.py` SHALL accept a `fix: bool` parameter. When `fix=True`, after running validation it SHALL iterate over issues, check `FIXERS` for each issue's `check` name, call the fixer if available, and report results.

The output SHALL show:
- `[FIXED]` prefix for successfully fixed issues
- `[SKIP]` prefix for non-fixable issues
- A summary line: "Fixed N of M issues. K require manual attention."

#### Scenario: Fix mode runs fixers
- **WHEN** `_run_validate(fix=True)` runs and finds 3 fixable issues and 2 non-fixable issues
- **THEN** the 3 fixable issues SHALL have their fixers called and 2 non-fixable issues SHALL be reported as `[SKIP]`

#### Scenario: Fix mode with no fixable issues
- **WHEN** `_run_validate(fix=True)` runs and all issues are non-fixable
- **THEN** all issues SHALL be reported as `[SKIP]` and the summary SHALL show "Fixed 0 of N issues"

### Requirement: lexictl validate --fix flag
The `lexictl validate` command SHALL accept a `--fix` flag. This flag SHALL NOT be available on `lexi validate` (agent CLI).

#### Scenario: lexictl validate --fix
- **WHEN** running `lexictl validate --fix`
- **THEN** fixable issues SHALL be auto-remediated and results displayed

#### Scenario: lexi validate --fix not available
- **WHEN** running `lexi validate --fix`
- **THEN** the `--fix` flag SHALL NOT be recognized (it is lexictl-only)
