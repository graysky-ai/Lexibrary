## ADDED Requirements

### Requirement: ValidationReport counts by severity
The `ValidationReport` SHALL provide a `counts_by_severity() -> dict[str, int]` method that returns a dictionary with keys `"error"`, `"warning"`, and `"info"` mapped to their respective issue counts.

#### Scenario: Counts all severities
- **WHEN** calling `counts_by_severity()` on a report with 2 errors, 3 warnings, and 1 info issue
- **THEN** the result SHALL be `{"error": 2, "warning": 3, "info": 1}`

#### Scenario: Empty report counts
- **WHEN** calling `counts_by_severity()` on an empty report
- **THEN** the result SHALL be `{"error": 0, "warning": 0, "info": 0}`

### Requirement: CI mode validation output
The `_run_validate()` function in `src/lexibrary/cli/_shared.py` SHALL accept a `ci_mode: bool` parameter. When `ci_mode=True`, the output SHALL be a single compact line: `lexibrary-validate: errors=N warnings=N info=N`. No Rich formatting SHALL be used in CI mode.

#### Scenario: CI mode compact output
- **WHEN** `_run_validate(ci_mode=True)` runs and finds 1 error and 2 warnings
- **THEN** the output SHALL be `lexibrary-validate: errors=1 warnings=2 info=0`

#### Scenario: CI mode clean output
- **WHEN** `_run_validate(ci_mode=True)` runs and finds no issues
- **THEN** the output SHALL be `lexibrary-validate: errors=0 warnings=0 info=0`

### Requirement: lexictl validate --ci flag
The `lexictl validate` command SHALL accept a `--ci` flag that enables CI mode: compact single-line output and strict exit codes. Exit code contract: 0=no errors, 1=errors found, 2=internal failure.

#### Scenario: CI flag passed through
- **WHEN** running `lexictl validate --ci`
- **THEN** `_run_validate()` SHALL be called with `ci_mode=True`

#### Scenario: CI exit code 0
- **WHEN** running `lexictl validate --ci` with no errors
- **THEN** the exit code SHALL be 0

#### Scenario: CI exit code 1
- **WHEN** running `lexictl validate --ci` and errors exist
- **THEN** the exit code SHALL be 1
