"""Unit tests for :mod:`lexibrary.curator.validation_fixers`.

Covers the translation layer that turns a curator :class:`TriageItem` into a
validator :class:`ValidationIssue`, dispatches it through the
``FIXERS`` registry, and maps the resulting ``FixResult`` onto a
:class:`SubAgentResult` with the correct ``outcome``.

These tests use monkeypatching to substitute a fake fixer into the
registry — they do not need a real filesystem layout because the bridge
itself is filesystem-agnostic.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.models import CollectItem, SubAgentResult, TriageItem
from lexibrary.curator.validation_fixers import fix_validation_issue
from lexibrary.validator.fixes import FIXERS, FixResult
from lexibrary.validator.report import ValidationIssue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(
    *,
    check: str,
    action_key: str,
    path: Path | None = Path("src/example.py"),
    severity: str = "warning",
    message: str = "test message",
) -> TriageItem:
    """Build a TriageItem with a validation-style CollectItem."""
    collect = CollectItem(
        source="validation",
        path=path,
        severity=severity,  # type: ignore[arg-type]
        message=message,
        check=check,
    )
    return TriageItem(
        source_item=collect,
        issue_type="consistency",
        action_key=action_key,
        priority=10.0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFixValidationIssueRouting:
    """The bridge looks up the fixer in FIXERS using the check name."""

    def test_routes_to_fixers(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        captured: dict[str, object] = {}

        def fake_fixer(
            issue: ValidationIssue,
            project_root: Path,
            config: LexibraryConfig,
        ) -> FixResult:
            captured["issue"] = issue
            captured["project_root"] = project_root
            captured["config"] = config
            return FixResult(
                check=issue.check,
                path=Path("src/example.py"),
                fixed=True,
                message="ok",
            )

        monkeypatch.setitem(FIXERS, "hash_freshness", fake_fixer)

        config = LexibraryConfig()
        item = _make_item(check="hash_freshness", action_key="fix_hash_freshness")

        result = fix_validation_issue(item, tmp_path, config)

        # The fixer was called with a faithful round-trip of CollectItem state.
        assert "issue" in captured
        issue = captured["issue"]
        assert isinstance(issue, ValidationIssue)
        assert issue.check == "hash_freshness"
        assert issue.severity == "warning"
        assert issue.message == "test message"
        # path.as_posix() is used for cross-platform artifact strings.
        assert issue.artifact == "src/example.py"
        assert captured["project_root"] == tmp_path
        assert captured["config"] is config

        assert isinstance(result, SubAgentResult)
        assert result.action_key == "fix_hash_freshness"
        assert result.outcome == "fixed"
        assert result.success is True


class TestFixValidationIssueMissingFixer:
    """An unknown check returns ``outcome='no_fixer'``."""

    def test_missing_check_reports_no_fixer(self, tmp_path: Path) -> None:
        config = LexibraryConfig()
        item = _make_item(
            check="nonexistent_check",
            action_key="autofix_validation_issue",
        )

        result = fix_validation_issue(item, tmp_path, config)

        assert result.outcome == "no_fixer"
        assert result.success is False
        assert result.action_key == "autofix_validation_issue"
        assert "no_fixer_registered" in result.message
        assert "nonexistent_check" in result.message

    def test_empty_check_reports_no_fixer(self, tmp_path: Path) -> None:
        """Items with an empty check string still produce a readable message."""
        config = LexibraryConfig()
        item = _make_item(check="", action_key="autofix_validation_issue")

        result = fix_validation_issue(item, tmp_path, config)

        assert result.outcome == "no_fixer"
        assert "no_fixer_registered" in result.message


class TestFixValidationIssueExceptionPath:
    """A fixer that raises is converted to ``outcome='errored'``."""

    def test_handles_fixer_exception(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        def exploding_fixer(
            issue: ValidationIssue,
            project_root: Path,
            config: LexibraryConfig,
        ) -> FixResult:
            raise RuntimeError("boom")

        monkeypatch.setitem(FIXERS, "hash_freshness", exploding_fixer)

        config = LexibraryConfig()
        item = _make_item(check="hash_freshness", action_key="fix_hash_freshness")

        result = fix_validation_issue(item, tmp_path, config)

        assert result.outcome == "errored"
        assert result.success is False
        assert "boom" in result.message
        assert result.action_key == "fix_hash_freshness"


class TestFixValidationIssueResultMapping:
    """Success and failure from :class:`FixResult` map to the correct outcome."""

    def test_success_result(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        def fake_fixer(
            issue: ValidationIssue,
            project_root: Path,
            config: LexibraryConfig,
        ) -> FixResult:
            return FixResult(
                check=issue.check,
                path=Path("src/example.py"),
                fixed=True,
                message="re-generated design file",
            )

        monkeypatch.setitem(FIXERS, "hash_freshness", fake_fixer)

        config = LexibraryConfig()
        item = _make_item(check="hash_freshness", action_key="fix_hash_freshness")

        result = fix_validation_issue(item, tmp_path, config)

        assert result.outcome == "fixed"
        assert result.success is True
        assert result.message == "re-generated design file"
        assert result.path == Path("src/example.py")
        assert result.llm_calls == 0

    def test_failure_result(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        def fake_fixer(
            issue: ValidationIssue,
            project_root: Path,
            config: LexibraryConfig,
        ) -> FixResult:
            return FixResult(
                check=issue.check,
                path=Path("src/example.py"),
                fixed=False,
                message="source file not found",
            )

        monkeypatch.setitem(FIXERS, "hash_freshness", fake_fixer)

        config = LexibraryConfig()
        item = _make_item(check="hash_freshness", action_key="fix_hash_freshness")

        result = fix_validation_issue(item, tmp_path, config)

        assert result.outcome == "fixer_failed"
        assert result.success is False
        assert result.message == "source file not found"

    def test_preserves_narrow_action_key(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """The per-check action_key is preserved — not replaced by the umbrella."""

        def fake_fixer(
            issue: ValidationIssue,
            project_root: Path,
            config: LexibraryConfig,
        ) -> FixResult:
            return FixResult(check=issue.check, path=tmp_path, fixed=True, message="ok")

        monkeypatch.setitem(FIXERS, "orphaned_designs", fake_fixer)

        config = LexibraryConfig()
        item = _make_item(check="orphaned_designs", action_key="fix_orphaned_designs")

        result = fix_validation_issue(item, tmp_path, config)

        assert result.action_key == "fix_orphaned_designs"
        assert result.action_key != "autofix_validation_issue"

    def test_none_path_produces_empty_artifact(
        self,
        tmp_path: Path,
        monkeypatch,  # type: ignore[no-untyped-def]
    ) -> None:
        """When the collect item has no path, artifact is the empty string."""
        captured: dict[str, ValidationIssue] = {}

        def fake_fixer(
            issue: ValidationIssue,
            project_root: Path,
            config: LexibraryConfig,
        ) -> FixResult:
            captured["issue"] = issue
            return FixResult(check=issue.check, path=project_root, fixed=True, message="ok")

        monkeypatch.setitem(FIXERS, "hash_freshness", fake_fixer)

        config = LexibraryConfig()
        item = _make_item(check="hash_freshness", action_key="fix_hash_freshness", path=None)

        fix_validation_issue(item, tmp_path, config)

        assert captured["issue"].artifact == ""
