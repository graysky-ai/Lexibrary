# validator/report

**Summary:** Validation report models -- `ValidationIssue`, `ValidationSummary`, and `ValidationReport` dataclasses with Rich rendering and JSON serialization support.

## Interface

| Name | Key Fields / Signature | Purpose |
| --- | --- | --- |
| `Severity` | `Literal["error", "warning", "info"]` | Type alias for severity levels |
| `ValidationIssue` | `severity`, `check`, `message`, `artifact`, `suggestion=""` | Frozen dataclass representing a single validation finding |
| `ValidationIssue.to_dict` | `() -> dict[str, str]` | JSON-serializable dictionary |
| `ValidationSummary` | `error_count`, `warning_count`, `info_count` | Frozen dataclass with aggregate counts |
| `ValidationSummary.total` | `-> int` | Sum of all severity counts |
| `ValidationSummary.to_dict` | `() -> dict[str, int]` | JSON-serializable dictionary (includes `total`) |
| `ValidationReport` | `issues: list[ValidationIssue]` | Mutable dataclass aggregating all issues |
| `ValidationReport.summary` | `-> ValidationSummary` | Computed property counting issues by severity |
| `ValidationReport.has_errors` | `() -> bool` | True if any error-severity issues exist |
| `ValidationReport.has_warnings` | `() -> bool` | True if any warning-severity issues exist |
| `ValidationReport.exit_code` | `() -> int` | 0=clean, 1=errors present, 2=warnings only |
| `ValidationReport.to_dict` | `() -> dict[str, object]` | Full report as JSON-serializable dict (`issues` + `summary`) |
| `ValidationReport.render` | `(console: Console) -> None` | Rich rendering grouped by severity with tables and summary line |

## Rendering Details

- Empty reports print "No validation issues found." in bold green
- Issues grouped by severity in display order: error, warning, info
- Each group has a header with symbol + count, then a 4-column Rich table (Check, Artifact, Message, Suggestion)
- Summary line uses Rich markup for color-coded counts

## Exit Code Convention

| Condition | Code |
| --- | --- |
| No errors or warnings | 0 |
| At least one error | 1 |
| Warnings but no errors | 2 |

## Dependencies

- `rich.console.Console`, `rich.table.Table`, `rich.text.Text`

## Dependents

- `lexibrarian.validator.__init__` -- imports and re-exports all models
- `lexibrarian.validator.checks` -- imports `ValidationIssue` to create findings
- `lexibrarian.cli` -- renders report and uses exit codes
