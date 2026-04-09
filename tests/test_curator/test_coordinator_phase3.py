"""Tests for Phase 3 coordinator extensions.

Covers: budget issue collection, comment audit collection, triage
classification of budget and audit issues, dispatch routing to
Budget Trimmer and Comment Auditor sub-agents, scoped runs,
Phase 3 report fields, and autonomy gating for high-risk condensation.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.models import (
    BudgetCollectItem,
    CollectItem,
    CollectResult,
    CommentAuditCollectItem,
    CuratorReport,
    DispatchResult,
    SubAgentResult,
    TriageItem,
    TriageResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_minimal_project(tmp_path: Path) -> Path:
    """Create a minimal .lexibrary project structure."""
    lex_dir = tmp_path / ".lexibrary"
    lex_dir.mkdir()
    (lex_dir / "designs").mkdir()
    (lex_dir / "curator").mkdir()
    return tmp_path


def _make_source_file(project_root: Path, rel_path: str, content: str) -> Path:
    """Create a source file under project_root and return its absolute path."""
    p = project_root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _make_design_file(
    project_root: Path,
    source_rel: str,
    *,
    source_hash: str = "abc123",
    interface_hash: str | None = None,
    updated_by: str = "archivist",
    preserved_sections: dict[str, str] | None = None,
) -> Path:
    """Create a minimal design file matching a source path."""
    design_dir = project_root / ".lexibrary" / "designs" / source_rel
    design_path = Path(str(design_dir) + ".md") if design_dir.suffix else design_dir / "index.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Test design file",
            id=source_rel.replace("/", "-").replace(".", "-"),
            updated_by=updated_by,
            status="active",
        ),
        summary="Test summary",
        interface_contract="def foo(): ...",
        dependencies=[],
        dependents=[],
        preserved_sections=preserved_sections or {},
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=source_hash,
            interface_hash=interface_hash,
            generated=datetime.now(UTC),
            generator="test",
        ),
    )
    content = serialize_design_file(df)
    design_path.write_text(content, encoding="utf-8")
    return design_path


def _make_oversized_design_file(project_root: Path, source_rel: str) -> Path:
    """Create a design file that exceeds the default 4000-token budget.

    Uses preserved_sections to inject large content that actually gets
    serialized to the file.  At chars/4, we need ~16000+ chars to exceed
    the 4000-token budget.
    """
    large_content = "This is filler content for testing. " * 600  # ~21600 chars = ~5400 tokens
    return _make_design_file(
        project_root,
        source_rel,
        preserved_sections={"Insights": large_content},
    )


def _make_source_with_todos(project_root: Path, rel_path: str) -> Path:
    """Create a source file containing TODO/FIXME/HACK markers."""
    content = '''\
"""Module with various TODO markers for testing."""

from __future__ import annotations


def function_one():
    """Does something."""
    # TODO: add validation for edge cases
    return 42


def function_two():
    """Does something else."""
    # FIXME(alice): this breaks on empty input
    return None


def function_three():
    """Clean function, no issues."""
    return True


def function_four():
    # HACK: temporary workaround for timezone bug
    import datetime
    return datetime.datetime.now()
'''
    return _make_source_file(project_root, rel_path, content)


# ---------------------------------------------------------------------------
# Collect phase: budget issues
# ---------------------------------------------------------------------------


class TestCollectBudgetIssues:
    """Collect phase detects over-budget knowledge-layer files."""

    def test_collect_includes_budget_issues(self, tmp_path: Path) -> None:
        """Over-budget design files appear in collect result."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        _make_oversized_design_file(project, "src/foo.py")

        config = LexibraryConfig()
        coord = Coordinator(project, config)
        result = coord._collect()

        assert len(result.budget_items) >= 1
        budget_issue = result.budget_items[0]
        assert budget_issue.current_tokens > budget_issue.budget_target
        assert budget_issue.file_type == "design_file"

    def test_collect_skips_within_budget(self, tmp_path: Path) -> None:
        """Design files within budget are not flagged."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/bar.py", "def bar(): pass\n")
        _make_design_file(project, "src/bar.py")

        config = LexibraryConfig()
        coord = Coordinator(project, config)
        result = coord._collect()

        assert len(result.budget_items) == 0

    def test_collect_budget_respects_scope(self, tmp_path: Path) -> None:
        """Budget scanning respects scope filtering."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/a.py", "def a(): pass\n")
        _make_oversized_design_file(project, "src/a.py")
        _make_source_file(project, "src/b.py", "def b(): pass\n")
        _make_oversized_design_file(project, "src/b.py")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        # Scope to a.py design file path
        design_a = project / ".lexibrary" / "designs" / "src" / "a.py.md"
        result = coord._collect(scope=design_a)

        # Only a.py's budget issue should be collected
        paths = [bi.path for bi in result.budget_items]
        assert design_a in paths
        design_b = project / ".lexibrary" / "designs" / "src" / "b.py.md"
        assert design_b not in paths


# ---------------------------------------------------------------------------
# Collect phase: comment audit issues
# ---------------------------------------------------------------------------


class TestCollectCommentAuditIssues:
    """Collect phase detects TODO/FIXME/HACK markers in source files."""

    def test_collect_includes_todo_markers(self, tmp_path: Path) -> None:
        """Source files with TODO markers produce comment audit items."""
        project = _setup_minimal_project(tmp_path)
        _make_source_with_todos(project, "src/mod.py")

        config = LexibraryConfig()
        coord = Coordinator(project, config)
        result = coord._collect()

        assert len(result.comment_audit_items) >= 3  # TODO, FIXME, HACK
        marker_types = {item.marker_type for item in result.comment_audit_items}
        assert "TODO" in marker_types
        assert "FIXME" in marker_types
        assert "HACK" in marker_types

    def test_collect_no_todos_empty_result(self, tmp_path: Path) -> None:
        """Clean source files produce no comment audit items."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/clean.py", "def clean(): pass\n")

        config = LexibraryConfig()
        coord = Coordinator(project, config)
        result = coord._collect()

        assert len(result.comment_audit_items) == 0

    def test_collect_comment_audit_respects_scope(self, tmp_path: Path) -> None:
        """Comment audit scanning respects scope filtering."""
        project = _setup_minimal_project(tmp_path)
        _make_source_with_todos(project, "src/lexibrary/a.py")
        _make_source_with_todos(project, "src/lexibrary/b.py")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        # Scope to only src/lexibrary/a.py
        scope_path = project / "src" / "lexibrary" / "a.py"
        result = coord._collect(scope=scope_path)

        # Only a.py's markers should be collected
        paths = {item.path for item in result.comment_audit_items}
        assert scope_path in paths
        assert (project / "src" / "lexibrary" / "b.py") not in paths


# ---------------------------------------------------------------------------
# Triage phase: budget and audit classification
# ---------------------------------------------------------------------------


class TestTriageBudgetAndAudit:
    """Triage correctly classifies budget and comment audit issues."""

    def test_triage_classifies_budget_issues(self, tmp_path: Path) -> None:
        """Budget issues are classified as 'budget' type with 'condense_file' action."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect_result = CollectResult(
            budget_items=[
                BudgetCollectItem(
                    path=Path("/tmp/designs/test.md"),
                    current_tokens=5000,
                    budget_target=4000,
                    file_type="design_file",
                ),
            ]
        )

        triage_result = coord._triage(collect_result)
        budget_items = [t for t in triage_result.items if t.issue_type == "budget"]
        assert len(budget_items) == 1
        assert budget_items[0].action_key == "condense_file"
        assert budget_items[0].risk_level == "high"

    def test_triage_classifies_comment_audit_issues(self, tmp_path: Path) -> None:
        """Comment audit issues are classified with 'flag_stale_comment' action."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect_result = CollectResult(
            comment_audit_items=[
                CommentAuditCollectItem(
                    path=Path("/tmp/src/test.py"),
                    line_number=10,
                    comment_text="# TODO: fix this",
                    code_context="def foo():\n    # TODO: fix this\n    pass",
                    marker_type="TODO",
                ),
            ]
        )

        triage_result = coord._triage(collect_result)
        audit_items = [t for t in triage_result.items if t.issue_type == "comment_audit"]
        assert len(audit_items) == 1
        assert audit_items[0].action_key == "flag_stale_comment"
        assert audit_items[0].risk_level == "medium"

    def test_triage_budget_priority_scales_with_overage(self, tmp_path: Path) -> None:
        """Budget issues with larger overages get higher priority."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect_result = CollectResult(
            budget_items=[
                BudgetCollectItem(
                    path=Path("/tmp/designs/small.md"),
                    current_tokens=4500,
                    budget_target=4000,
                    file_type="design_file",
                ),
                BudgetCollectItem(
                    path=Path("/tmp/designs/large.md"),
                    current_tokens=8000,
                    budget_target=4000,
                    file_type="design_file",
                ),
            ]
        )

        triage_result = coord._triage(collect_result)
        budget_items = [t for t in triage_result.items if t.issue_type == "budget"]
        assert len(budget_items) == 2
        # Large overage should have higher priority
        large = [t for t in budget_items if t.budget_item and t.budget_item.current_tokens == 8000]
        small = [t for t in budget_items if t.budget_item and t.budget_item.current_tokens == 4500]
        assert large[0].priority > small[0].priority


# ---------------------------------------------------------------------------
# Dispatch phase: budget and comment audit routing
# ---------------------------------------------------------------------------


class TestDispatchBudgetAndAudit:
    """Dispatch routes budget and audit issues to correct sub-agents."""

    @pytest.mark.asyncio
    async def test_dispatch_routes_budget_to_condense(self, tmp_path: Path) -> None:
        """Budget issues dispatch to condense_file() under full autonomy."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
        coord = Coordinator(project, config)

        budget_item = BudgetCollectItem(
            path=project / ".lexibrary" / "designs" / "src" / "foo.py.md",
            current_tokens=5000,
            budget_target=4000,
            file_type="design_file",
        )

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="validation",
                        path=budget_item.path,
                        severity="warning",
                        message="Over budget",
                        check="budget",
                    ),
                    issue_type="budget",
                    action_key="condense_file",
                    priority=50.0,
                    budget_item=budget_item,
                    risk_level="high",
                ),
            ]
        )

        mock_result = MagicMock()
        mock_result.condensed_content = "condensed"
        mock_result.trimmed_sections = ["Section A"]
        mock_result.success = True

        with patch(
            "lexibrary.curator.coordinator.Coordinator._dispatch_budget_condense",
            new_callable=AsyncMock,
        ) as mock_condense:
            mock_condense.return_value = SubAgentResult(
                success=True,
                action_key="condense_file",
                path=budget_item.path,
                message="Condensed",
                llm_calls=1,
            )
            result = await coord._dispatch(triage)

        assert len(result.dispatched) == 1
        assert result.dispatched[0].action_key == "condense_file"
        assert result.dispatched[0].success

    @pytest.mark.asyncio
    async def test_dispatch_routes_comment_audit(self, tmp_path: Path) -> None:
        """Comment audit issues dispatch to audit_comment() under full autonomy."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
        coord = Coordinator(project, config)

        audit_item = CommentAuditCollectItem(
            path=project / "src" / "foo.py",
            line_number=10,
            comment_text="# TODO: fix this",
            code_context="def foo():\n    # TODO: fix this\n    pass",
            marker_type="TODO",
        )

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="validation",
                        path=audit_item.path,
                        severity="info",
                        message="TODO at line 10",
                        check="comment_audit",
                    ),
                    issue_type="comment_audit",
                    action_key="flag_stale_comment",
                    priority=25.0,
                    comment_audit_item=audit_item,
                    risk_level="medium",
                ),
            ]
        )

        with patch(
            "lexibrary.curator.coordinator.Coordinator._dispatch_comment_audit",
            new_callable=AsyncMock,
        ) as mock_audit:
            mock_audit.return_value = SubAgentResult(
                success=True,
                action_key="flag_stale_comment",
                path=audit_item.path,
                message="TODO at line 10: stale",
                llm_calls=1,
            )
            result = await coord._dispatch(triage)

        assert len(result.dispatched) == 1
        assert result.dispatched[0].action_key == "flag_stale_comment"
        assert result.dispatched[0].success

    @pytest.mark.asyncio
    async def test_dispatch_auto_low_proposes_condensation(self, tmp_path: Path) -> None:
        """Under auto_low, condense_file (High risk) is NOT auto-executed."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()  # Default: auto_low
        coord = Coordinator(project, config)

        budget_item = BudgetCollectItem(
            path=project / ".lexibrary" / "designs" / "src" / "foo.py.md",
            current_tokens=5000,
            budget_target=4000,
            file_type="design_file",
        )

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="validation",
                        path=budget_item.path,
                        severity="warning",
                        message="Over budget",
                        check="budget",
                    ),
                    issue_type="budget",
                    action_key="condense_file",
                    priority=50.0,
                    budget_item=budget_item,
                    risk_level="high",
                ),
            ]
        )

        result = await coord._dispatch(triage)

        # Under auto_low, condense_file is High risk -> deferred
        assert len(result.dispatched) == 0
        assert len(result.deferred) == 1


# ---------------------------------------------------------------------------
# Scoped run
# ---------------------------------------------------------------------------


class TestScopedRun:
    """Scoped runs limit collect to the specified path."""

    def test_scoped_collect_limits_budget_scanning(self, tmp_path: Path) -> None:
        """Scoped collect only gathers budget issues for the specified path."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/a.py", "def a(): pass\n")
        _make_oversized_design_file(project, "src/a.py")
        _make_source_file(project, "src/b.py", "def b(): pass\n")
        _make_oversized_design_file(project, "src/b.py")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        design_a = project / ".lexibrary" / "designs" / "src" / "a.py.md"
        result = coord._collect(scope=design_a)

        # Only a.py's budget issue should be collected
        budget_paths = [bi.path for bi in result.budget_items]
        assert design_a in budget_paths
        design_b = project / ".lexibrary" / "designs" / "src" / "b.py.md"
        assert design_b not in budget_paths

    def test_scoped_collect_limits_comment_audit(self, tmp_path: Path) -> None:
        """Scoped collect only gathers comment audit issues for the specified path."""
        project = _setup_minimal_project(tmp_path)
        _make_source_with_todos(project, "src/lexibrary/a.py")
        _make_source_with_todos(project, "src/lexibrary/b.py")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        scope_path = project / "src" / "lexibrary" / "a.py"
        result = coord._collect(scope=scope_path)

        # Only a.py's markers should be collected
        paths = {item.path for item in result.comment_audit_items}
        assert scope_path in paths
        assert (project / "src" / "lexibrary" / "b.py") not in paths


# ---------------------------------------------------------------------------
# Report Phase 3 fields
# ---------------------------------------------------------------------------


class TestReportPhase3Fields:
    """Report includes Phase 3 counts and trigger field."""

    def test_report_includes_budget_counts(self, tmp_path: Path) -> None:
        """Report includes budget_condensed and budget_proposed counts."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult()
        triage = TriageResult()
        dispatch = DispatchResult(
            dispatched=[
                SubAgentResult(
                    success=True,
                    action_key="condense_file",
                    path=Path("/tmp/a.md"),
                    message="Condensed",
                    llm_calls=1,
                ),
                SubAgentResult(
                    success=True,
                    action_key="propose_condensation",
                    path=Path("/tmp/b.md"),
                    message="Proposed",
                    llm_calls=1,
                ),
            ]
        )

        report = coord._report(collect, triage, dispatch)
        assert report.budget_condensed == 1
        assert report.budget_proposed == 1

    def test_report_includes_audit_counts(self, tmp_path: Path) -> None:
        """Report includes comments_flagged, descriptions_audited, summaries_audited."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult()
        triage = TriageResult()
        dispatch = DispatchResult(
            dispatched=[
                SubAgentResult(
                    success=True,
                    action_key="flag_stale_comment",
                    path=Path("/tmp/src/a.py"),
                    message="stale",
                    llm_calls=1,
                ),
                SubAgentResult(
                    success=True,
                    action_key="flag_stale_comment",
                    path=Path("/tmp/src/b.py"),
                    message="stale",
                    llm_calls=1,
                ),
                SubAgentResult(
                    success=True,
                    action_key="audit_description",
                    path=Path("/tmp/designs/a.md"),
                    message="quality=0.5",
                    llm_calls=1,
                ),
                SubAgentResult(
                    success=True,
                    action_key="audit_summary",
                    path=Path("/tmp/designs/b.md"),
                    message="quality=0.6",
                    llm_calls=1,
                ),
            ]
        )

        report = coord._report(collect, triage, dispatch)
        assert report.comments_flagged == 2
        assert report.descriptions_audited == 1
        assert report.summaries_audited == 1

    def test_report_trigger_field(self, tmp_path: Path) -> None:
        """Report trigger field reflects how the run was initiated."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult()
        triage = TriageResult()
        dispatch = DispatchResult()

        report = coord._report(collect, triage, dispatch, trigger="reactive_post_edit")
        assert report.trigger == "reactive_post_edit"

    def test_report_default_trigger(self, tmp_path: Path) -> None:
        """Report defaults trigger to 'on_demand'."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult()
        triage = TriageResult()
        dispatch = DispatchResult()

        report = coord._report(collect, triage, dispatch)
        assert report.trigger == "on_demand"

    def test_report_invalid_trigger_falls_back(self, tmp_path: Path) -> None:
        """Invalid trigger values fall back to 'on_demand'."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult()
        triage = TriageResult()
        dispatch = DispatchResult()

        report = coord._report(collect, triage, dispatch, trigger="nonexistent")
        assert report.trigger == "on_demand"


# ---------------------------------------------------------------------------
# Full pipeline with Phase 3
# ---------------------------------------------------------------------------


class TestFullPipelinePhase3:
    """End-to-end pipeline tests for Phase 3 features."""

    @pytest.mark.asyncio
    async def test_pipeline_with_trigger(self, tmp_path: Path) -> None:
        """Pipeline passes trigger through to report."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        report = await coord.run(trigger="reactive_post_bead_close")
        assert report.trigger == "reactive_post_bead_close"

    @pytest.mark.asyncio
    async def test_pipeline_default_trigger(self, tmp_path: Path) -> None:
        """Pipeline defaults trigger to 'on_demand'."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        report = await coord.run()
        assert report.trigger == "on_demand"
