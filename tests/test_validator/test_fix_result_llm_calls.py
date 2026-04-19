"""Tests for :class:`FixResult.llm_calls` plumbing (curator-4 Group 2).

Verifies that ``FixResult`` carries an honest ``llm_calls`` count, that
:func:`fix_wikilink_resolution` reports ``llm_calls=1`` when it actually
invokes :func:`update_file`, and that
:func:`lexibrary.curator.validation_fixers.fix_validation_issue`
propagates that count into :class:`SubAgentResult.llm_calls` for the
``fixed`` and ``fixer_failed`` outcomes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig, ScopeRoot, TokenBudgetConfig
from lexibrary.curator.models import CollectItem, SubAgentResult, TriageItem
from lexibrary.curator.validation_fixers import fix_validation_issue
from lexibrary.validator.fixes import FIXERS, FixResult, fix_wikilink_resolution
from lexibrary.validator.report import ValidationIssue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(scope_root: str = ".") -> LexibraryConfig:
    return LexibraryConfig(
        scope_roots=[ScopeRoot(path=scope_root)],
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
    )


def _make_issue(
    check: str = "wikilink_resolution",
    artifact: str = ".lexibrary/designs/src/foo.py.md",
    severity: str = "error",
    message: str = "[[NonexistentConcept]] does not resolve",
) -> ValidationIssue:
    return ValidationIssue(
        severity=severity,  # type: ignore[arg-type]
        check=check,
        message=message,
        artifact=artifact,
    )


def _make_triage_item(
    *,
    check: str = "wikilink_resolution",
    action_key: str = "fix_wikilink_resolution",
    path: Path | None = Path("src/foo.py"),
    severity: str = "error",
    message: str = "wikilink failed to resolve",
) -> TriageItem:
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


def _write_design_with_source(
    tmp_path: Path,
    source_rel: str,
    *,
    write_source: bool = True,
) -> tuple[Path, Path]:
    """Write a parseable design file + optional source path."""
    design_path = tmp_path / ".lexibrary" / "designs" / (source_rel + ".md")
    design_path.parent.mkdir(parents=True, exist_ok=True)
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=f"Design for {source_rel}",
            id=source_rel.replace("/", "-").replace(".", "-"),
            updated_by="archivist",
            status="active",
        ),
        summary=f"Summary of {source_rel}",
        interface_contract="def foo(): ...",
        dependencies=[],
        dependents=[],
        wikilinks=["NonexistentConcept"],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="abc123",
            interface_hash=None,
            generated=datetime.now(UTC),
            generator="test",
        ),
    )
    design_path.write_text(serialize_design_file(df), encoding="utf-8")

    source_path = tmp_path / source_rel
    if write_source:
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text("def foo(): pass\n", encoding="utf-8")
    return design_path, source_path


# ---------------------------------------------------------------------------
# (a) FixResult default
# ---------------------------------------------------------------------------


class TestFixResultDefault:
    """The new ``llm_calls`` field defaults to ``0``."""

    def test_default_llm_calls_is_zero(self) -> None:
        result = FixResult(
            check="hash_freshness",
            path=Path("src/foo.py"),
            fixed=True,
            message="ok",
        )
        assert result.llm_calls == 0

    def test_llm_calls_round_trips(self) -> None:
        result = FixResult(
            check="wikilink_resolution",
            path=Path(".lexibrary/designs/src/foo.py.md"),
            fixed=True,
            message="re-generated",
            llm_calls=1,
        )
        assert result.llm_calls == 1


# ---------------------------------------------------------------------------
# (b) fix_wikilink_resolution returns llm_calls=1 on happy path
# ---------------------------------------------------------------------------


class TestFixWikilinkResolutionLlmCalls:
    """``fix_wikilink_resolution`` honestly reports its BAML invocation."""

    def test_successful_regeneration_reports_one_llm_call(self, tmp_path: Path) -> None:
        """Happy path must return ``llm_calls=1`` — update_file was invoked."""
        design_path, _ = _write_design_with_source(tmp_path, "src/foo.py")
        issue = _make_issue(
            check="wikilink_resolution",
            artifact=str(design_path.relative_to(tmp_path)),
        )
        config = _make_config()

        from lexibrary.archivist.change_checker import ChangeLevel
        from lexibrary.archivist.pipeline import FileResult

        mock_update = AsyncMock(return_value=FileResult(change=ChangeLevel.CONTENT_CHANGED))

        with (
            patch("lexibrary.archivist.pipeline.update_file", mock_update),
            patch("lexibrary.archivist.service.build_archivist_service", return_value=object()),
        ):
            result = fix_wikilink_resolution(issue, tmp_path, config)

        assert result.fixed is True
        assert result.llm_calls == 1

    def test_failed_regeneration_reports_zero_llm_calls(self, tmp_path: Path) -> None:
        """When ``update_file`` returns ``failed=True``, the fixer returns
        ``fixed=False`` via an early non-LLM path — we still charge the call."""
        design_path, _ = _write_design_with_source(tmp_path, "src/foo.py")
        issue = _make_issue(
            check="wikilink_resolution",
            artifact=str(design_path.relative_to(tmp_path)),
        )
        config = _make_config()

        from lexibrary.archivist.change_checker import ChangeLevel
        from lexibrary.archivist.pipeline import FileResult

        mock_update = AsyncMock(
            return_value=FileResult(change=ChangeLevel.CONTENT_CHANGED, failed=True)
        )

        with (
            patch("lexibrary.archivist.pipeline.update_file", mock_update),
            patch("lexibrary.archivist.service.build_archivist_service", return_value=object()),
        ):
            result = fix_wikilink_resolution(issue, tmp_path, config)

        # The design path exists, the source exists, the LLM was invoked but
        # returned failed=True. Per Group 2 spec, only the happy path sets
        # llm_calls=1; the failed branch (which is an "error branch" from the
        # fixer's perspective) keeps llm_calls=0 so we don't charge a failed
        # invocation against the budget.
        assert result.fixed is False
        assert result.llm_calls == 0

    def test_stack_post_reports_zero_llm_calls(self, tmp_path: Path) -> None:
        """Non-design artifacts short-circuit without invoking the LLM."""
        issue = _make_issue(
            check="wikilink_resolution",
            artifact=".lexibrary/stack/ST-001-example.md",
        )
        result = fix_wikilink_resolution(issue, tmp_path, _make_config())
        assert result.fixed is False
        assert result.llm_calls == 0

    def test_missing_design_reports_zero_llm_calls(self, tmp_path: Path) -> None:
        """Design file not on disk — no LLM invocation."""
        issue = _make_issue(
            check="wikilink_resolution",
            artifact=".lexibrary/designs/src/missing.py.md",
        )
        result = fix_wikilink_resolution(issue, tmp_path, _make_config())
        assert result.fixed is False
        assert result.llm_calls == 0


# ---------------------------------------------------------------------------
# (c) Bridge propagates FixResult.llm_calls into SubAgentResult.llm_calls
# ---------------------------------------------------------------------------


class TestBridgePropagatesLlmCalls:
    """``fix_validation_issue`` forwards ``llm_calls`` for fixed/fixer_failed."""

    def test_propagates_on_success(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        def fake_fixer(
            issue: ValidationIssue,
            project_root: Path,
            config: LexibraryConfig,
        ) -> FixResult:
            return FixResult(
                check=issue.check,
                path=Path("src/foo.py"),
                fixed=True,
                message="re-generated",
                llm_calls=1,
            )

        monkeypatch.setitem(FIXERS, "wikilink_resolution", fake_fixer)

        config = LexibraryConfig()
        item = _make_triage_item(
            check="wikilink_resolution",
            action_key="fix_wikilink_resolution",
        )

        result = fix_validation_issue(item, tmp_path, config)

        assert isinstance(result, SubAgentResult)
        assert result.outcome == "fixed"
        assert result.success is True
        assert result.llm_calls == 1

    def test_propagates_on_fixer_failed(self, tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """A fixer that ran an LLM call but returned fixed=False still charges
        its llm_calls into the SubAgentResult (honest reporting)."""

        def fake_fixer(
            issue: ValidationIssue,
            project_root: Path,
            config: LexibraryConfig,
        ) -> FixResult:
            return FixResult(
                check=issue.check,
                path=Path("src/foo.py"),
                fixed=False,
                message="condensation did not reduce below budget",
                llm_calls=1,
            )

        monkeypatch.setitem(FIXERS, "wikilink_resolution", fake_fixer)

        config = LexibraryConfig()
        item = _make_triage_item(
            check="wikilink_resolution",
            action_key="fix_wikilink_resolution",
        )

        result = fix_validation_issue(item, tmp_path, config)

        assert result.outcome == "fixer_failed"
        assert result.success is False
        assert result.llm_calls == 1

    def test_no_fixer_registered_reports_zero_llm_calls(self, tmp_path: Path) -> None:
        """The no-fixer path never invokes the LLM — llm_calls stays 0."""
        config = LexibraryConfig()
        item = _make_triage_item(
            check="nonexistent_check",
            action_key="autofix_validation_issue",
        )

        result = fix_validation_issue(item, tmp_path, config)

        assert result.outcome == "no_fixer"
        assert result.llm_calls == 0

    def test_errored_branch_reports_zero_llm_calls(
        self,
        tmp_path: Path,
        monkeypatch,  # type: ignore[no-untyped-def]
    ) -> None:
        """A fixer that raises — we cannot tell how much of the LLM call
        completed before the raise, so we conservatively charge zero."""

        def exploding_fixer(
            issue: ValidationIssue,
            project_root: Path,
            config: LexibraryConfig,
        ) -> FixResult:
            raise RuntimeError("boom")

        monkeypatch.setitem(FIXERS, "wikilink_resolution", exploding_fixer)

        config = LexibraryConfig()
        item = _make_triage_item(
            check="wikilink_resolution",
            action_key="fix_wikilink_resolution",
        )

        result = fix_validation_issue(item, tmp_path, config)

        assert result.outcome == "errored"
        assert result.llm_calls == 0
