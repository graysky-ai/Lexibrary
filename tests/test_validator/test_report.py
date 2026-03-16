"""Unit tests for ValidationReport, ValidationIssue, and ValidationSummary."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from lexibrary.validator import ValidationIssue, ValidationReport, ValidationSummary


def _make_issue(
    severity: str = "error",
    check: str = "test_check",
    message: str = "test message",
    artifact: str = "test/artifact.py",
    suggestion: str = "",
) -> ValidationIssue:
    """Helper to create a ValidationIssue with defaults."""
    return ValidationIssue(
        severity=severity,  # type: ignore[arg-type]
        check=check,
        message=message,
        artifact=artifact,
        suggestion=suggestion,
    )


# ---------------------------------------------------------------------------
# ValidationIssue
# ---------------------------------------------------------------------------


class TestValidationIssue:
    """Tests for the ValidationIssue dataclass."""

    def test_required_fields(self) -> None:
        issue = _make_issue()
        assert issue.severity == "error"
        assert issue.check == "test_check"
        assert issue.message == "test message"
        assert issue.artifact == "test/artifact.py"

    def test_suggestion_defaults_empty(self) -> None:
        issue = _make_issue()
        assert issue.suggestion == ""

    def test_suggestion_set(self) -> None:
        issue = _make_issue(suggestion="Try X instead")
        assert issue.suggestion == "Try X instead"

    def test_to_dict(self) -> None:
        issue = _make_issue(
            severity="warning",
            check="hash_freshness",
            message="Stale hash",
            artifact="src/foo.py.md",
            suggestion="Run lexictl update",
        )
        d = issue.to_dict()
        assert d == {
            "severity": "warning",
            "check": "hash_freshness",
            "message": "Stale hash",
            "artifact": "src/foo.py.md",
            "suggestion": "Run lexictl update",
        }

    def test_frozen(self) -> None:
        issue = _make_issue()
        try:
            issue.severity = "info"  # type: ignore[misc]
            raise AssertionError("Expected FrozenInstanceError")
        except AttributeError:
            pass


# ---------------------------------------------------------------------------
# ValidationSummary
# ---------------------------------------------------------------------------


class TestValidationSummary:
    """Tests for the ValidationSummary dataclass."""

    def test_defaults_all_zero(self) -> None:
        s = ValidationSummary()
        assert s.error_count == 0
        assert s.warning_count == 0
        assert s.info_count == 0
        assert s.total == 0

    def test_total_sums_all(self) -> None:
        s = ValidationSummary(error_count=2, warning_count=3, info_count=5)
        assert s.total == 10

    def test_to_dict(self) -> None:
        s = ValidationSummary(error_count=1, warning_count=2, info_count=3)
        d = s.to_dict()
        assert d == {
            "error_count": 1,
            "warning_count": 2,
            "info_count": 3,
            "total": 6,
        }


# ---------------------------------------------------------------------------
# ValidationReport — exit codes
# ---------------------------------------------------------------------------


class TestValidationReportExitCodes:
    """Tests for exit_code() logic."""

    def test_empty_report_exit_0(self) -> None:
        report = ValidationReport()
        assert report.exit_code() == 0

    def test_info_only_exit_0(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="info"),
                _make_issue(severity="info"),
            ]
        )
        assert report.exit_code() == 0

    def test_errors_exit_1(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="error"),
            ]
        )
        assert report.exit_code() == 1

    def test_errors_and_warnings_exit_1(self) -> None:
        """Errors take precedence over warnings."""
        report = ValidationReport(
            issues=[
                _make_issue(severity="error"),
                _make_issue(severity="warning"),
            ]
        )
        assert report.exit_code() == 1

    def test_warnings_only_exit_2(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="warning"),
            ]
        )
        assert report.exit_code() == 2

    def test_warnings_and_info_exit_2(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="warning"),
                _make_issue(severity="info"),
            ]
        )
        assert report.exit_code() == 2


# ---------------------------------------------------------------------------
# ValidationReport — has_errors / has_warnings
# ---------------------------------------------------------------------------


class TestValidationReportHasMethods:
    """Tests for has_errors() and has_warnings()."""

    def test_empty_report(self) -> None:
        report = ValidationReport()
        assert report.has_errors() is False
        assert report.has_warnings() is False

    def test_has_errors_true(self) -> None:
        report = ValidationReport(issues=[_make_issue(severity="error")])
        assert report.has_errors() is True

    def test_has_errors_false_with_warnings(self) -> None:
        report = ValidationReport(issues=[_make_issue(severity="warning")])
        assert report.has_errors() is False

    def test_has_warnings_true(self) -> None:
        report = ValidationReport(issues=[_make_issue(severity="warning")])
        assert report.has_warnings() is True

    def test_has_warnings_false_with_info(self) -> None:
        report = ValidationReport(issues=[_make_issue(severity="info")])
        assert report.has_warnings() is False


# ---------------------------------------------------------------------------
# ValidationReport — to_dict (JSON serialization)
# ---------------------------------------------------------------------------


class TestValidationReportToDict:
    """Tests for to_dict() serialization."""

    def test_empty_report(self) -> None:
        report = ValidationReport()
        d = report.to_dict()
        assert d["issues"] == []
        assert d["summary"] == {
            "error_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "total": 0,
        }

    def test_mixed_issues(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="error", check="c1", message="m1", artifact="a1"),
                _make_issue(severity="warning", check="c2", message="m2", artifact="a2"),
                _make_issue(severity="info", check="c3", message="m3", artifact="a3"),
            ]
        )
        d = report.to_dict()
        assert len(d["issues"]) == 3
        assert d["summary"]["error_count"] == 1
        assert d["summary"]["warning_count"] == 1
        assert d["summary"]["info_count"] == 1
        assert d["summary"]["total"] == 3

    def test_issues_are_dicts(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="error", suggestion="fix it"),
            ]
        )
        d = report.to_dict()
        issue = d["issues"][0]
        assert isinstance(issue, dict)
        assert issue["severity"] == "error"
        assert issue["suggestion"] == "fix it"

    def test_json_serializable(self) -> None:
        """Verify to_dict() output can be passed through json.dumps."""
        import json

        report = ValidationReport(
            issues=[
                _make_issue(severity="error"),
                _make_issue(severity="warning"),
            ]
        )
        serialized = json.dumps(report.to_dict())
        parsed = json.loads(serialized)
        assert parsed["summary"]["total"] == 2


# ---------------------------------------------------------------------------
# ValidationReport — summary property
# ---------------------------------------------------------------------------


class TestValidationReportSummary:
    """Tests for the computed summary property."""

    def test_empty_summary(self) -> None:
        report = ValidationReport()
        s = report.summary
        assert s.error_count == 0
        assert s.warning_count == 0
        assert s.info_count == 0

    def test_summary_counts_correct(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="error"),
                _make_issue(severity="error"),
                _make_issue(severity="warning"),
                _make_issue(severity="info"),
                _make_issue(severity="info"),
                _make_issue(severity="info"),
            ]
        )
        s = report.summary
        assert s.error_count == 2
        assert s.warning_count == 1
        assert s.info_count == 3


# ---------------------------------------------------------------------------
# ValidationReport — render (Rich output)
# ---------------------------------------------------------------------------


class TestValidationReportRender:
    """Tests for Rich rendering."""

    @staticmethod
    def _capture_render(report: ValidationReport) -> str:
        buf = StringIO()
        with patch("lexibrary.cli._output.sys.stdout", buf):
            report.render()
        return buf.getvalue()

    def test_empty_report_shows_clean_message(self) -> None:
        output = self._capture_render(ValidationReport())
        assert "No validation issues found" in output

    def test_errors_section_shown(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="error", message="broken link"),
            ]
        )
        output = self._capture_render(report)
        assert "Errors (1)" in output
        assert "broken link" in output

    def test_warnings_section_shown(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="warning", message="stale hash"),
            ]
        )
        output = self._capture_render(report)
        assert "Warnings (1)" in output
        assert "stale hash" in output

    def test_info_section_shown(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="info", message="unindexed dir"),
            ]
        )
        output = self._capture_render(report)
        assert "Infos (1)" in output
        assert "unindexed dir" in output

    def test_mixed_report_shows_all_sections(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="error", message="err1"),
                _make_issue(severity="warning", message="warn1"),
                _make_issue(severity="warning", message="warn2"),
                _make_issue(severity="info", message="info1"),
            ]
        )
        output = self._capture_render(report)
        assert "Errors (1)" in output
        assert "Warnings (2)" in output
        assert "Infos (1)" in output
        assert "Summary:" in output

    def test_summary_line_in_output(self) -> None:
        report = ValidationReport(
            issues=[
                _make_issue(severity="error"),
            ]
        )
        output = self._capture_render(report)
        assert "1 error(s)" in output


# ---------------------------------------------------------------------------
# Public API re-exports
# ---------------------------------------------------------------------------


class TestPublicAPI:
    """Verify that the public API is importable from the validator package."""

    def test_imports(self) -> None:
        from lexibrary.validator import (  # noqa: F401
            ValidationIssue,
            ValidationReport,
            ValidationSummary,
            validate_library,
        )

    def test_validate_library_returns_report(self) -> None:
        from pathlib import Path

        from lexibrary.validator import validate_library

        report = validate_library(Path("."), Path(".lexibrary"))
        assert isinstance(report, ValidationReport)
