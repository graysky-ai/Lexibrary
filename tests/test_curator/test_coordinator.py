"""Tests for the curator coordinator skeleton.

Covers: initialization, collect phase, triage, dispatch, report,
graceful degradation, ErrorSummary accumulation, idempotency,
scope isolation, and concurrency lock.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import (
    Coordinator,
    CuratorLockError,
    _acquire_lock,
    _lock_path,
    _release_lock,
)
from lexibrary.curator.models import (
    CollectItem,
    CollectResult,
    CuratorReport,
    DispatchResult,
    SubAgentResult,
    TriageItem,
    TriageResult,
)
from lexibrary.validator.report import ValidationIssue, ValidationReport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
) -> Path:
    """Create a minimal design file matching a source path."""

    design_dir = project_root / ".lexibrary" / "designs" / source_rel
    # e.g. src/foo.py -> .lexibrary/designs/src/foo.py.md
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


def _make_iwh_file(
    project_root: Path,
    source_rel_dir: str,
    *,
    scope: str = "incomplete",
    body: str = "test iwh",
    hours_ago: int = 0,
) -> Path:
    """Create an IWH signal file in the .lexibrary mirror."""
    mirror_dir = project_root / ".lexibrary" / source_rel_dir
    mirror_dir.mkdir(parents=True, exist_ok=True)
    iwh_path = mirror_dir / ".iwh"
    created = datetime.now(UTC) - timedelta(hours=hours_ago)
    content = (
        f"---\nauthor: test-agent\ncreated: {created.isoformat()}\nscope: {scope}\n---\n{body}\n"
    )
    iwh_path.write_text(content, encoding="utf-8")
    return iwh_path


def _setup_minimal_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with .lexibrary structure."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".lexibrary").mkdir()
    (project / ".lexibrary" / "designs").mkdir()
    (project / ".lexibrary" / "config.yaml").write_text("", encoding="utf-8")
    return project


def _run_coordinator(project: Path, **kwargs: object) -> CuratorReport:
    """Convenience helper to run the coordinator synchronously."""
    config = LexibraryConfig()
    coord = Coordinator(project, config)
    return asyncio.run(coord.run(**kwargs))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestCoordinatorInit:
    """Coordinator initialises without error."""

    def test_init_creates_coordinator(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)
        assert coord.project_root == project
        assert coord.curator_config.autonomy == "auto_low"

    def test_init_with_custom_config(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate(
            {"curator": {"autonomy": "full", "max_llm_calls_per_run": 10}}
        )
        coord = Coordinator(project, config)
        assert coord.curator_config.autonomy == "full"
        assert coord.curator_config.max_llm_calls_per_run == 10


# ---------------------------------------------------------------------------
# Collect phase
# ---------------------------------------------------------------------------


class TestCollectPhase:
    """Collect phase discovers issues from multiple sources."""

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_collect_discovers_stale_design(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "# updated content\ndef foo(): pass\n")
        _make_design_file(project, "src/foo.py", source_hash="old_hash")

        config = LexibraryConfig()
        coord = Coordinator(project, config)
        result = coord._collect()

        staleness_items = [
            i for i in result.items if i.source == "staleness" and i.check == "staleness"
        ]
        assert len(staleness_items) >= 1
        assert staleness_items[0].source_hash_stale

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_collect_validation_error_logged(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        """When validate_library raises, the error is recorded and collection continues."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        with patch(
            "lexibrary.validator.validate_library",
            side_effect=RuntimeError("boom"),
        ):
            result = coord._collect()

        # The error is caught and recorded
        assert result.validation_error is not None
        assert "boom" in result.validation_error
        assert coord.summary.has_errors()

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_collect_iwh_signals(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        project = _setup_minimal_project(tmp_path)
        _make_iwh_file(project, "src/module", scope="incomplete", body="needs work")

        config = LexibraryConfig()
        coord = Coordinator(project, config)
        result = coord._collect()

        iwh_items = [i for i in result.items if i.source == "iwh"]
        assert len(iwh_items) >= 1

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_collect_validates_library(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        """validate_library() raising does not crash the coordinator."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        with patch(
            "lexibrary.validator.validate_library",
            side_effect=RuntimeError("validation explosion"),
        ):
            result = coord._collect()

        assert result.validation_error is not None
        assert "validation explosion" in result.validation_error
        assert coord.summary.has_errors()

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_collect_no_database_skips_graph(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        with patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None):
            result = coord._collect()

        assert result.link_graph_available is False


# ---------------------------------------------------------------------------
# Triage phase
# ---------------------------------------------------------------------------


class TestTriagePhase:
    """Triage classifies and prioritises collected items."""

    def test_triage_classifies_staleness(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="staleness",
                    path=Path("src/foo.py"),
                    severity="warning",
                    message="stale",
                    check="staleness",
                    source_hash_stale=True,
                    interface_hash_stale=True,
                    updated_by="archivist",
                ),
            ]
        )

        result = coord._triage(collect)
        assert len(result.items) == 1
        assert result.items[0].issue_type == "staleness"
        assert result.items[0].action_key == "regenerate_stale_design"

    def test_triage_agent_edited_classified_separately(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="staleness",
                    path=Path("src/foo.py"),
                    severity="warning",
                    message="stale",
                    check="staleness",
                    source_hash_stale=True,
                    interface_hash_stale=False,
                    updated_by="agent",
                ),
            ]
        )

        result = coord._triage(collect)
        assert len(result.items) == 1
        assert result.items[0].agent_edited is True
        assert result.items[0].action_key == "reconcile_agent_interface_stable"

    def test_triage_agent_interface_changed(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="staleness",
                    path=Path("src/foo.py"),
                    severity="warning",
                    message="stale",
                    check="staleness",
                    source_hash_stale=True,
                    interface_hash_stale=True,
                    updated_by="agent",
                ),
            ]
        )

        result = coord._triage(collect)
        assert result.items[0].action_key == "reconcile_agent_interface_changed"

    def test_triage_priority_ordering(self, tmp_path: Path) -> None:
        """Interface hash changes rank higher than content-only."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="staleness",
                    path=Path("src/low.py"),
                    severity="info",
                    message="stale",
                    check="staleness",
                    source_hash_stale=True,
                    interface_hash_stale=False,
                    updated_by="archivist",
                ),
                CollectItem(
                    source="staleness",
                    path=Path("src/high.py"),
                    severity="warning",
                    message="stale",
                    check="staleness",
                    source_hash_stale=True,
                    interface_hash_stale=True,
                    updated_by="archivist",
                ),
            ]
        )

        result = coord._triage(collect)
        assert len(result.items) == 2
        # The interface-hash-stale item should be first (higher priority)
        assert result.items[0].source_item.path == Path("src/high.py")
        assert result.items[1].source_item.path == Path("src/low.py")

    def test_triage_skips_scope_isolation_items(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="staleness",
                    path=Path("src/skip.py"),
                    severity="info",
                    message="Skipped -- uncommitted changes detected",
                    check="scope_isolation",
                ),
            ]
        )

        result = coord._triage(collect)
        assert len(result.items) == 0

    def test_triage_classifies_validation_issues(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="validation",
                    path=Path("some/artifact"),
                    severity="info",
                    message="unhandled check",
                    check="check_with_no_fixer",
                ),
            ]
        )

        result = coord._triage(collect)
        assert len(result.items) == 1
        assert result.items[0].issue_type == "consistency"
        # ``check_with_no_fixer`` is not in CHECK_TO_ACTION_KEY, so the
        # classifier falls back to the umbrella key.
        assert result.items[0].action_key == "autofix_validation_issue"

    def test_triage_classifies_validation_uses_per_check_action_key(self, tmp_path: Path) -> None:
        """CHECK_TO_ACTION_KEY drives action_key for checks with registered fixers."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="validation",
                    path=Path("src/foo.py"),
                    severity="warning",
                    message="stale source hash",
                    check="hash_freshness",
                ),
                CollectItem(
                    source="validation",
                    path=Path("designs/src/foo.py.md"),
                    severity="warning",
                    message="orphan design",
                    check="orphaned_designs",
                ),
            ]
        )

        result = coord._triage(collect)
        action_keys = {item.action_key for item in result.items}
        assert "fix_hash_freshness" in action_keys
        assert "fix_orphaned_designs" in action_keys
        assert "autofix_validation_issue" not in action_keys

    def test_triage_classifies_iwh(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="iwh",
                    path=Path("src/module"),
                    severity="info",
                    message="IWH signal: scope=blocked, body=stuck",
                    check="iwh_scan",
                ),
            ]
        )

        result = coord._triage(collect)
        assert len(result.items) == 1
        assert result.items[0].action_key == "promote_blocked_iwh"


# ---------------------------------------------------------------------------
# Dispatch phase
# ---------------------------------------------------------------------------


class TestDispatchPhase:
    """Dispatch phase applies autonomy gating and calls sub-agents."""

    @pytest.mark.asyncio
    async def test_dispatch_auto_low_dispatches_low(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="staleness",
                        path=Path("src/foo.py"),
                        severity="info",
                        message="stale",
                        check="staleness",
                    ),
                    issue_type="staleness",
                    action_key="regenerate_stale_design",
                    priority=50.0,
                ),
            ]
        )

        result = await coord._dispatch(triage)
        assert len(result.dispatched) == 1
        assert len(result.deferred) == 0

    @pytest.mark.asyncio
    async def test_dispatch_auto_low_defers_medium(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="staleness",
                        path=Path("src/foo.py"),
                        severity="warning",
                        message="stale",
                        check="staleness",
                    ),
                    issue_type="staleness",
                    action_key="reconcile_agent_interface_changed",
                    priority=150.0,
                ),
            ]
        )

        result = await coord._dispatch(triage)
        assert len(result.dispatched) == 0
        assert len(result.deferred) == 1

    @pytest.mark.asyncio
    async def test_dispatch_full_dispatches_all(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
        coord = Coordinator(project, config)

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="staleness",
                        path=Path("src/foo.py"),
                        severity="warning",
                        message="stale",
                        check="staleness",
                    ),
                    issue_type="staleness",
                    action_key="reconcile_agent_interface_changed",
                    priority=150.0,
                ),
            ]
        )

        result = await coord._dispatch(triage)
        assert len(result.dispatched) == 1
        assert len(result.deferred) == 0

    @pytest.mark.asyncio
    async def test_dispatch_propose_defers_all(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate({"curator": {"autonomy": "propose"}})
        coord = Coordinator(project, config)

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="staleness",
                        path=Path("src/foo.py"),
                        severity="info",
                        message="stale",
                        check="staleness",
                    ),
                    issue_type="staleness",
                    action_key="regenerate_stale_design",
                    priority=50.0,
                ),
            ]
        )

        result = await coord._dispatch(triage)
        assert len(result.dispatched) == 0
        assert len(result.deferred) == 1

    @pytest.mark.asyncio
    async def test_dispatch_llm_cap_reached(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate(
            {"curator": {"autonomy": "full", "max_llm_calls_per_run": 1}}
        )
        coord = Coordinator(project, config)

        # Create real source and design files so reconciliation can succeed
        source_a = _make_source_file(project, "src/a.py", "def a(): pass\n")
        _make_design_file(project, "src/a.py", source_hash="old_a", updated_by="agent")
        source_b = _make_source_file(project, "src/b.py", "def b(): pass\n")
        _make_design_file(project, "src/b.py", source_hash="old_b", updated_by="agent")

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="staleness",
                        path=source_a,
                        severity="warning",
                        message="stale",
                        check="staleness",
                    ),
                    issue_type="reconciliation",
                    action_key="reconcile_agent_interface_changed",
                    priority=150.0,
                    agent_edited=True,
                    risk_level="medium",
                ),
                TriageItem(
                    source_item=CollectItem(
                        source="staleness",
                        path=source_b,
                        severity="warning",
                        message="stale",
                        check="staleness",
                    ),
                    issue_type="reconciliation",
                    action_key="reconcile_agent_interface_changed",
                    priority=140.0,
                    agent_edited=True,
                    risk_level="medium",
                ),
            ]
        )

        result = await coord._dispatch(triage)
        # First dispatches (1 LLM call from reconciliation), second deferred
        assert len(result.dispatched) == 1
        assert len(result.deferred) == 1
        assert result.llm_cap_reached is True

    @pytest.mark.asyncio
    async def test_dispatch_dry_run(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="staleness",
                        path=Path("src/foo.py"),
                        severity="info",
                        message="stale",
                        check="staleness",
                    ),
                    issue_type="staleness",
                    action_key="regenerate_stale_design",
                    priority=50.0,
                ),
            ]
        )

        result = await coord._dispatch(triage, dry_run=True)
        assert len(result.dispatched) == 1
        assert "dry-run" in result.dispatched[0].message

    @pytest.mark.asyncio
    async def test_dispatch_validation_issue_calls_validation_fixers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Validation action keys route through ``fix_validation_issue``."""
        from lexibrary.curator import validation_fixers

        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        captured: dict[str, object] = {}

        def fake_bridge(
            item: TriageItem,
            project_root: Path,
            cfg: LexibraryConfig,
        ) -> SubAgentResult:
            captured["item"] = item
            captured["project_root"] = project_root
            captured["config"] = cfg
            return SubAgentResult(
                success=True,
                action_key=item.action_key,
                path=item.source_item.path,
                message="fake fixed",
                llm_calls=0,
                outcome="fixed",
            )

        monkeypatch.setattr(validation_fixers, "fix_validation_issue", fake_bridge)

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="validation",
                        path=Path("src/foo.py"),
                        severity="warning",
                        message="stale source hash",
                        check="hash_freshness",
                    ),
                    issue_type="consistency",
                    action_key="fix_hash_freshness",
                    priority=40.0,
                ),
            ]
        )

        result = await coord._dispatch(triage)

        assert "item" in captured
        assert captured["project_root"] == project
        assert captured["config"] is config

        assert len(result.dispatched) == 1
        assert len(result.deferred) == 0
        dispatched = result.dispatched[0]
        assert dispatched.action_key == "fix_hash_freshness"
        assert dispatched.outcome == "fixed"

    @pytest.mark.asyncio
    async def test_dispatch_validation_issue_not_stubbed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Validation dispatch reports outcome ``fixed``, not ``stubbed``."""
        from lexibrary.curator import validation_fixers

        project = _setup_minimal_project(tmp_path)

        def fake_bridge(
            item: TriageItem,
            project_root: Path,
            cfg: LexibraryConfig,
        ) -> SubAgentResult:
            return SubAgentResult(
                success=True,
                action_key=item.action_key,
                path=item.source_item.path,
                message="fake fixed",
                llm_calls=0,
                outcome="fixed",
            )

        monkeypatch.setattr(validation_fixers, "fix_validation_issue", fake_bridge)

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="validation",
                        path=Path("designs/src/foo.py.md"),
                        severity="warning",
                        message="orphan design",
                        check="orphaned_designs",
                    ),
                    issue_type="consistency",
                    # fix_orphaned_designs is Medium risk → needs full autonomy
                    action_key="fix_orphaned_designs",
                    priority=40.0,
                ),
            ]
        )

        # Medium-risk dispatch requires full autonomy — rebuild with full config.
        config_full = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
        coord_full = Coordinator(project, config_full)
        result = await coord_full._dispatch(triage)

        assert len(result.dispatched) == 1
        dispatched = result.dispatched[0]
        assert dispatched.outcome == "fixed"
        assert dispatched.outcome != "stubbed"

    @pytest.mark.asyncio
    async def test_validation_fixer_not_called_in_dry_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dry-run mode short-circuits before calling the validation bridge."""
        from lexibrary.curator import validation_fixers

        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        called: list[bool] = []

        def fake_bridge(
            item: TriageItem,
            project_root: Path,
            cfg: LexibraryConfig,
        ) -> SubAgentResult:
            called.append(True)
            return SubAgentResult(
                success=True,
                action_key=item.action_key,
                path=None,
                message="should not be called",
                llm_calls=0,
                outcome="fixed",
            )

        monkeypatch.setattr(validation_fixers, "fix_validation_issue", fake_bridge)

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="validation",
                        path=Path("src/foo.py"),
                        severity="warning",
                        message="stale source hash",
                        check="hash_freshness",
                    ),
                    issue_type="consistency",
                    action_key="fix_hash_freshness",
                    priority=40.0,
                ),
            ]
        )

        result = await coord._dispatch(triage, dry_run=True)

        assert called == []
        assert len(result.dispatched) == 1
        assert result.dispatched[0].outcome == "dry_run"


# ---------------------------------------------------------------------------
# Report phase
# ---------------------------------------------------------------------------


class TestReportPhase:
    """Report phase aggregates results and writes to disk."""

    def test_report_has_correct_counts(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult()
        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="staleness",
                        path=Path("src/foo.py"),
                        severity="info",
                        message="stale",
                        check="staleness",
                    ),
                    issue_type="staleness",
                    action_key="regenerate_stale_design",
                    priority=50.0,
                ),
            ]
        )
        dispatch = DispatchResult(
            dispatched=[
                SubAgentResult(
                    success=True,
                    action_key="regenerate_stale_design",
                    path=Path("src/foo.py"),
                    message="stub: done",
                ),
            ],
            deferred=[],
        )

        report = coord._report(collect, triage, dispatch)
        assert report.checked == 1
        assert report.fixed == 1
        assert report.deferred == 0
        assert report.errored == 0

    def test_report_writes_json_file(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult()
        triage = TriageResult()
        dispatch = DispatchResult()

        report = coord._report(collect, triage, dispatch)
        assert report.report_path is not None
        assert report.report_path.exists()
        data = json.loads(report.report_path.read_text(encoding="utf-8"))
        assert "checked" in data
        assert "timestamp" in data

    def test_report_tracks_sub_agent_calls(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        dispatch = DispatchResult(
            dispatched=[
                SubAgentResult(success=True, action_key="regenerate_stale_design"),
                SubAgentResult(success=True, action_key="regenerate_stale_design"),
                SubAgentResult(success=True, action_key="autofix_validation_issue"),
            ],
        )

        report = coord._report(CollectResult(), TriageResult(), dispatch)
        assert report.sub_agent_calls["regenerate_stale_design"] == 2
        assert report.sub_agent_calls["autofix_validation_issue"] == 1


# ---------------------------------------------------------------------------
# ErrorSummary accumulation
# ---------------------------------------------------------------------------


class TestErrorSummary:
    """ErrorSummary accumulates across phases."""

    def test_errors_from_collect_appear_in_report(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        # Simulate an error in collect
        coord.summary.add("collect", RuntimeError("bad parse"), path="src/broken.py")

        report = coord._report(CollectResult(), TriageResult(), DispatchResult())
        assert report.errored == 1
        assert report.errors[0]["phase"] == "collect"
        assert "bad parse" in report.errors[0]["message"]

    def test_errors_from_dispatch_appear_in_report(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        # Simulate errors in both phases
        coord.summary.add("collect", RuntimeError("parse error"), path="src/a.py")
        coord.summary.add("dispatch", RuntimeError("sub-agent fail"), path="src/b.py")

        report = coord._report(CollectResult(), TriageResult(), DispatchResult())
        assert report.errored == 2
        phases = {e["phase"] for e in report.errors}
        assert phases == {"collect", "dispatch"}


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Coordinator degrades gracefully under adverse conditions."""

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_no_database_skips_graph_checks(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        with patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None):
            result = coord._collect()

        assert result.link_graph_available is False

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_validate_raises_logs_and_continues(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        with patch(
            "lexibrary.validator.validate_library",
            side_effect=RuntimeError("validator crashed"),
        ):
            result = coord._collect()

        assert result.validation_error is not None
        assert coord.summary.has_errors()
        # Other sources should still work
        assert isinstance(result, CollectResult)

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_unreadable_iwh_skipped(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        project = _setup_minimal_project(tmp_path)
        # Create a malformed IWH file
        iwh_dir = project / ".lexibrary" / "src" / "bad"
        iwh_dir.mkdir(parents=True)
        (iwh_dir / ".iwh").write_text("not valid yaml {{{}}}}", encoding="utf-8")

        config = LexibraryConfig()
        coord = Coordinator(project, config)
        result = coord._collect()

        # Should not crash -- malformed IWH silently skipped by find_all_iwh
        assert isinstance(result, CollectResult)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Second run with no changes produces zero dispatches."""

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_second_run_no_dispatches(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A clean project with no issues yields zero dispatches."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()

        # Patch validate_library to return empty report
        with patch(
            "lexibrary.validator.validate_library",
        ) as mock_validate:
            from lexibrary.validator.report import ValidationReport

            mock_validate.return_value = ValidationReport(issues=[])

            # First run
            coord1 = Coordinator(project, config)
            report1 = asyncio.run(coord1.run())
            assert report1.fixed == 0

            # Second run
            coord2 = Coordinator(project, config)
            report2 = asyncio.run(coord2.run())
            assert report2.fixed == 0
            assert report2.sub_agent_calls == {}


# ---------------------------------------------------------------------------
# Scope isolation
# ---------------------------------------------------------------------------


class TestScopeIsolation:
    """Uncommitted files and active IWH signals are skipped."""

    def test_uncommitted_files_skipped(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/dirty.py", "# dirty\n")
        _make_design_file(project, "src/dirty.py", source_hash="old")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        with (
            patch(
                "lexibrary.curator.coordinator._uncommitted_files",
                return_value={source},
            ),
            patch(
                "lexibrary.curator.coordinator._active_iwh_dirs",
                return_value=set(),
            ),
        ):
            result = coord._collect()

        # The file should be skipped, appearing as scope_isolation
        skipped = [i for i in result.items if i.check == "scope_isolation"]
        assert len(skipped) >= 1
        assert "uncommitted" in skipped[0].message

    def test_active_iwh_blocks_processing(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/module/foo.py", "# foo\n")
        _make_design_file(project, "src/module/foo.py", source_hash="old")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        with (
            patch(
                "lexibrary.curator.coordinator._uncommitted_files",
                return_value=set(),
            ),
            patch(
                "lexibrary.curator.coordinator._active_iwh_dirs",
                return_value={project / "src" / "module"},
            ),
        ):
            result = coord._collect()

        skipped = [i for i in result.items if i.check == "scope_isolation"]
        assert len(skipped) >= 1
        assert "IWH" in skipped[0].message

    def test_stale_iwh_does_not_block(self, tmp_path: Path) -> None:
        """IWH signals older than ttl_hours should NOT block."""
        project = _setup_minimal_project(tmp_path)
        # Create an old IWH (200 hours ago, well past default 72h ttl)
        _make_iwh_file(project, "src/module", hours_ago=200)

        result = _active_iwh_dirs(project, ttl_hours=72)
        assert len(result) == 0


def _active_iwh_dirs(project_root: Path, ttl_hours: int) -> set[Path]:
    """Direct call to the helper for testing."""
    from lexibrary.curator.coordinator import (
        _active_iwh_dirs as _real_active_iwh_dirs,
    )

    return _real_active_iwh_dirs(project_root, ttl_hours)


# ---------------------------------------------------------------------------
# Concurrency lock
# ---------------------------------------------------------------------------


class TestConcurrencyLock:
    """PID-file lock at .lexibrary/curator/.curator.lock."""

    def test_lock_acquired_when_no_lock_exists(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        lock = _acquire_lock(project)
        assert lock.exists()
        data = json.loads(lock.read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid()
        _release_lock(project)

    def test_live_lock_rejects_second_run(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        lock = _lock_path(project)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(
            json.dumps({"pid": os.getpid(), "timestamp": time.time()}),
            encoding="utf-8",
        )

        with pytest.raises(CuratorLockError, match="Another curator process"):
            _acquire_lock(project)

        _release_lock(project)

    def test_stale_lock_reclaimed(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        lock = _lock_path(project)
        lock.parent.mkdir(parents=True, exist_ok=True)
        # Write a lock with a dead PID and old timestamp
        lock.write_text(
            json.dumps(
                {
                    "pid": 99999999,  # almost certainly not running
                    "timestamp": time.time() - 3600,  # 1 hour ago
                }
            ),
            encoding="utf-8",
        )

        # Should reclaim the stale lock
        result = _acquire_lock(project)
        assert result.exists()
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["pid"] == os.getpid()
        _release_lock(project)

    def test_lock_released_on_cleanup(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        _acquire_lock(project)
        lock = _lock_path(project)
        assert lock.exists()
        _release_lock(project)
        assert not lock.exists()


# ---------------------------------------------------------------------------
# End-to-end skeleton run
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """End-to-end skeleton run produces a report file."""

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_full_run_produces_report(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "# updated\ndef bar(): pass\n")
        _make_design_file(project, "src/foo.py", source_hash="old_hash")

        with patch("lexibrary.validator.validate_library") as mock_validate:
            from lexibrary.validator.report import ValidationReport

            mock_validate.return_value = ValidationReport(issues=[])

            report = _run_coordinator(project)

        assert report.report_path is not None
        assert report.report_path.exists()
        assert report.checked >= 1

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_clean_project_zero_fixes(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        project = _setup_minimal_project(tmp_path)

        with patch("lexibrary.validator.validate_library") as mock_validate:
            from lexibrary.validator.report import ValidationReport

            mock_validate.return_value = ValidationReport(issues=[])

            report = _run_coordinator(project)

        assert report.fixed == 0
        assert report.errored == 0


# ---------------------------------------------------------------------------
# Deprecation dispatch flow (Phase 2 — Group 7)
# ---------------------------------------------------------------------------


class TestDeprecationCollect:
    """Collect phase detects deprecation candidates."""

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_collect_deleted_source_design(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        """Design file whose source is deleted is flagged as deprecation candidate."""
        project = _setup_minimal_project(tmp_path)
        # Create design file but no source file
        _make_design_file(project, "src/deleted.py", source_hash="abc")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        with (
            patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None),
            patch("lexibrary.linkgraph.query.open_index", return_value=None),
        ):
            result = coord._collect()

        dep_items = result.deprecation_items
        deleted_items = [d for d in dep_items if d.reason == "source_deleted"]
        assert len(deleted_items) >= 1
        assert deleted_items[0].artifact_kind == "design_file"

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_collect_orphan_concept(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        """Active concept with zero inbound refs is flagged as orphan."""
        project = _setup_minimal_project(tmp_path)
        concepts_dir = project / ".lexibrary" / "concepts"
        concepts_dir.mkdir(parents=True)
        concept_file = concepts_dir / "orphan-concept.md"
        content = (
            "---\ntitle: Orphan Concept\nid: orphan-concept\n"
            "status: active\ntags: [test]\n---\nBody\n"
        )
        concept_file.write_text(content, encoding="utf-8")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        # Mock link graph that returns empty reverse_deps
        mock_graph = MagicMock()
        mock_graph.reverse_deps.return_value = []
        mock_graph.traverse.return_value = []

        with (
            patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None),
            patch("lexibrary.linkgraph.query.open_index", return_value=mock_graph),
        ):
            result = coord._collect()

        orphan_items = [d for d in result.deprecation_items if d.reason == "orphan_zero_refs"]
        assert len(orphan_items) >= 1
        assert orphan_items[0].artifact_kind == "concept"


class TestDeprecationTriage:
    """Triage phase classifies deprecation candidates."""

    def test_triage_deprecation_orphan_concept(self, tmp_path: Path) -> None:
        """Orphan concept gets classified with deprecate_concept action key."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        from lexibrary.curator.models import DeprecationCollectItem

        collect = CollectResult(
            deprecation_items=[
                DeprecationCollectItem(
                    artifact_path=Path(".lexibrary/concepts/test.md"),
                    artifact_kind="concept",
                    current_status="active",
                    reason="orphan_zero_refs",
                ),
            ]
        )

        result = coord._triage(collect)
        dep_items = [t for t in result.items if t.issue_type == "deprecation"]
        assert len(dep_items) == 1
        assert dep_items[0].action_key == "deprecate_concept"
        assert dep_items[0].deprecation_item is not None

    def test_triage_deprecation_hard_delete(self, tmp_path: Path) -> None:
        """TTL-expired concept classified with hard_delete action key."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        from lexibrary.curator.models import DeprecationCollectItem

        collect = CollectResult(
            deprecation_items=[
                DeprecationCollectItem(
                    artifact_path=Path(".lexibrary/concepts/expired.md"),
                    artifact_kind="concept",
                    current_status="deprecated",
                    reason="ttl_expired_zero_refs",
                    commits_since_deprecation=60,
                ),
            ]
        )

        result = coord._triage(collect)
        dep_items = [t for t in result.items if t.issue_type == "deprecation"]
        assert len(dep_items) == 1
        assert dep_items[0].action_key == "hard_delete_concept_past_ttl"

    def test_triage_deprecation_ranking_by_risk(self, tmp_path: Path) -> None:
        """Deprecation items ranked: low risk first, then higher risk."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        from lexibrary.curator.models import DeprecationCollectItem

        collect = CollectResult(
            deprecation_items=[
                DeprecationCollectItem(
                    artifact_path=Path(".lexibrary/concepts/high.md"),
                    artifact_kind="concept",
                    current_status="active",
                    reason="orphan_zero_refs",
                ),
                DeprecationCollectItem(
                    artifact_path=Path(".lexibrary/concepts/low.md"),
                    artifact_kind="concept",
                    current_status="deprecated",
                    reason="ttl_expired_zero_refs",
                    commits_since_deprecation=60,
                ),
            ]
        )

        result = coord._triage(collect)
        dep_items = [t for t in result.items if t.issue_type == "deprecation"]
        assert len(dep_items) == 2
        # High-risk (deprecate_concept) should have higher priority than low-risk
        high_item = next(t for t in dep_items if t.action_key == "deprecate_concept")
        low_item = next(t for t in dep_items if t.action_key == "hard_delete_concept_past_ttl")
        assert high_item.priority > low_item.priority


class TestDeprecationDispatch:
    """Dispatch phase routes deprecation candidates correctly."""

    @pytest.mark.asyncio
    async def test_dispatch_auto_low_allows_hard_delete(self, tmp_path: Path) -> None:
        """Under auto_low, hard deletion (low risk) is dispatched."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()  # auto_low by default
        coord = Coordinator(project, config)

        from lexibrary.curator.models import DeprecationCollectItem

        dep_item = DeprecationCollectItem(
            artifact_path=project / ".lexibrary" / "concepts" / "expired.md",
            artifact_kind="concept",
            current_status="deprecated",
            reason="ttl_expired_zero_refs",
            commits_since_deprecation=60,
        )

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="deprecation",
                        path=dep_item.artifact_path,
                        severity="warning",
                        message="Deprecation candidate",
                        check="deprecation",
                    ),
                    issue_type="deprecation",
                    action_key="hard_delete_concept_past_ttl",
                    priority=20.0,
                    deprecation_item=dep_item,
                    risk_level="low",
                ),
            ]
        )

        # Mock the hard_delete to avoid actual file operations
        with patch("lexibrary.curator.lifecycle.dispatch_hard_delete") as mock_hd:
            mock_hd.return_value = SubAgentResult(
                success=True,
                action_key="hard_delete_concept_past_ttl",
                path=dep_item.artifact_path,
                message="Hard-deleted concept",
                llm_calls=0,
            )
            result = await coord._dispatch(triage)

        assert len(result.dispatched) == 1
        assert result.dispatched[0].success
        assert len(result.deferred) == 0

    @pytest.mark.asyncio
    async def test_dispatch_auto_low_defers_high_risk_deprecation(self, tmp_path: Path) -> None:
        """Under auto_low, concept deprecation (high risk) is deferred."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()  # auto_low by default
        coord = Coordinator(project, config)

        from lexibrary.curator.models import DeprecationCollectItem

        dep_item = DeprecationCollectItem(
            artifact_path=project / ".lexibrary" / "concepts" / "orphan.md",
            artifact_kind="concept",
            current_status="active",
            reason="orphan_zero_refs",
        )

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="deprecation",
                        path=dep_item.artifact_path,
                        severity="warning",
                        message="Deprecation candidate",
                        check="deprecation",
                    ),
                    issue_type="deprecation",
                    action_key="deprecate_concept",
                    priority=100.0,
                    deprecation_item=dep_item,
                    risk_level="high",
                ),
            ]
        )

        result = await coord._dispatch(triage)
        assert len(result.dispatched) == 0
        assert len(result.deferred) == 1

    @pytest.mark.asyncio
    async def test_dispatch_full_allows_concept_deprecation(self, tmp_path: Path) -> None:
        """Under full autonomy, concept deprecation is dispatched."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
        coord = Coordinator(project, config)

        from lexibrary.curator.models import DeprecationCollectItem

        dep_item = DeprecationCollectItem(
            artifact_path=project / ".lexibrary" / "concepts" / "orphan.md",
            artifact_kind="concept",
            current_status="active",
            reason="orphan_zero_refs",
        )

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="deprecation",
                        path=dep_item.artifact_path,
                        severity="warning",
                        message="Deprecation candidate",
                        check="deprecation",
                    ),
                    issue_type="deprecation",
                    action_key="deprecate_concept",
                    priority=100.0,
                    deprecation_item=dep_item,
                    risk_level="high",
                ),
            ]
        )

        # Mock the deprecation to avoid actual file operations
        with patch("lexibrary.curator.deprecation.dispatch_soft_deprecation") as mock_dep:
            mock_dep.return_value = SubAgentResult(
                success=True,
                action_key="deprecate_concept",
                path=dep_item.artifact_path,
                message="Deprecated concept",
                llm_calls=1,
            )
            result = await coord._dispatch(triage)

        assert len(result.dispatched) == 1
        assert result.dispatched[0].success
        assert len(result.deferred) == 0

    @pytest.mark.asyncio
    async def test_dispatch_confirmation_override_blocks_deprecation(self, tmp_path: Path) -> None:
        """With curator_deprecation_confirm=True, concept deprecation is deferred."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate(
            {
                "curator": {"autonomy": "full"},
                "concepts": {"curator_deprecation_confirm": True},
            }
        )
        coord = Coordinator(project, config)

        from lexibrary.curator.models import DeprecationCollectItem

        dep_item = DeprecationCollectItem(
            artifact_path=project / ".lexibrary" / "concepts" / "orphan.md",
            artifact_kind="concept",
            current_status="active",
            reason="orphan_zero_refs",
        )

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="deprecation",
                        path=dep_item.artifact_path,
                        severity="warning",
                        message="Deprecation candidate",
                        check="deprecation",
                    ),
                    issue_type="deprecation",
                    action_key="deprecate_concept",
                    priority=100.0,
                    deprecation_item=dep_item,
                    risk_level="high",
                ),
            ]
        )

        result = await coord._dispatch(triage)
        # Confirmation override should block even under full autonomy
        assert len(result.dispatched) == 0
        assert len(result.deferred) == 1

    @pytest.mark.asyncio
    async def test_dispatch_llm_cap_defers_deprecation(self, tmp_path: Path) -> None:
        """LLM cap enforcement defers deprecation actions."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate(
            {"curator": {"autonomy": "full", "max_llm_calls_per_run": 1}}
        )
        coord = Coordinator(project, config)

        from lexibrary.curator.models import DeprecationCollectItem

        dep_item_a = DeprecationCollectItem(
            artifact_path=project / ".lexibrary" / "concepts" / "first.md",
            artifact_kind="concept",
            current_status="active",
            reason="orphan_zero_refs",
        )
        dep_item_b = DeprecationCollectItem(
            artifact_path=project / ".lexibrary" / "concepts" / "second.md",
            artifact_kind="concept",
            current_status="active",
            reason="orphan_zero_refs",
        )

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="deprecation",
                        path=dep_item_a.artifact_path,
                        severity="warning",
                        message="Deprecation candidate",
                        check="deprecation",
                    ),
                    issue_type="deprecation",
                    action_key="deprecate_concept",
                    priority=100.0,
                    deprecation_item=dep_item_a,
                    risk_level="high",
                ),
                TriageItem(
                    source_item=CollectItem(
                        source="deprecation",
                        path=dep_item_b.artifact_path,
                        severity="warning",
                        message="Deprecation candidate",
                        check="deprecation",
                    ),
                    issue_type="deprecation",
                    action_key="deprecate_concept",
                    priority=90.0,
                    deprecation_item=dep_item_b,
                    risk_level="high",
                ),
            ]
        )

        # Mock the soft deprecation to return 1 LLM call
        with patch("lexibrary.curator.deprecation.dispatch_soft_deprecation") as mock_dep:
            mock_dep.return_value = SubAgentResult(
                success=True,
                action_key="deprecate_concept",
                path=dep_item_a.artifact_path,
                message="Deprecated concept",
                llm_calls=1,
            )
            result = await coord._dispatch(triage)

        # First item dispatched, second deferred due to LLM cap
        assert len(result.dispatched) == 1
        assert len(result.deferred) == 1
        assert result.llm_cap_reached

    @pytest.mark.asyncio
    async def test_dispatch_dry_run_records_deprecation(self, tmp_path: Path) -> None:
        """Dry-run mode records deprecation candidates without executing."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
        coord = Coordinator(project, config)

        from lexibrary.curator.models import DeprecationCollectItem

        dep_item = DeprecationCollectItem(
            artifact_path=project / ".lexibrary" / "concepts" / "orphan.md",
            artifact_kind="concept",
            current_status="active",
            reason="orphan_zero_refs",
        )

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="deprecation",
                        path=dep_item.artifact_path,
                        severity="warning",
                        message="Deprecation candidate",
                        check="deprecation",
                    ),
                    issue_type="deprecation",
                    action_key="deprecate_concept",
                    priority=100.0,
                    deprecation_item=dep_item,
                    risk_level="high",
                ),
            ]
        )

        result = await coord._dispatch(triage, dry_run=True)
        assert len(result.dispatched) == 1
        assert "dry-run" in result.dispatched[0].message
        assert result.dispatched[0].llm_calls == 0

    @pytest.mark.asyncio
    async def test_dispatch_iwh_signal_for_proposed_deprecation(self, tmp_path: Path) -> None:
        """IWH signal written when deprecation is gated by autonomy."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()  # auto_low -- blocks high risk
        coord = Coordinator(project, config)

        from lexibrary.curator.models import DeprecationCollectItem

        dep_item = DeprecationCollectItem(
            artifact_path=project / ".lexibrary" / "concepts" / "orphan.md",
            artifact_kind="concept",
            current_status="active",
            reason="orphan_zero_refs",
        )

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="deprecation",
                        path=dep_item.artifact_path,
                        severity="warning",
                        message="Deprecation candidate",
                        check="deprecation",
                    ),
                    issue_type="deprecation",
                    action_key="deprecate_concept",
                    priority=100.0,
                    deprecation_item=dep_item,
                    risk_level="high",
                ),
            ]
        )

        iwh_patch = "lexibrary.curator.coordinator.Coordinator._write_deprecation_proposal_iwh"
        with patch(iwh_patch) as mock_iwh:
            await coord._dispatch(triage)
            # IWH should have been called for the deferred deprecation
            mock_iwh.assert_called_once()

    def test_write_deprecation_proposal_iwh_writes_beside_artifact(self, tmp_path: Path) -> None:
        """Gated deprecation .iwh lands next to the artifact, not in a nested mirror.

        Regression: prior code prepended ``self.lexibrary_dir`` to a relative
        path that already began with ``.lexibrary/``, producing
        ``.lexibrary/.lexibrary/concepts/.iwh``.
        """
        from lexibrary.curator.models import DeprecationCollectItem

        project = _setup_minimal_project(tmp_path)
        (project / ".lexibrary" / "concepts").mkdir()
        artifact = project / ".lexibrary" / "concepts" / "CN-999-orphan.md"
        artifact.write_text("---\ntitle: orphan\n---\n", encoding="utf-8")

        coord = Coordinator(project, LexibraryConfig())

        dep_item = DeprecationCollectItem(
            artifact_path=artifact,
            artifact_kind="concept",
            current_status="active",
            reason="orphan_zero_refs",
        )
        triage_item = TriageItem(
            source_item=CollectItem(
                source="deprecation",
                path=artifact,
                severity="warning",
                message="Deprecation candidate",
                check="deprecation",
            ),
            issue_type="deprecation",
            action_key="deprecate_concept",
            priority=100.0,
            deprecation_item=dep_item,
            risk_level="high",
        )

        coord._write_deprecation_proposal_iwh(triage_item)

        expected = project / ".lexibrary" / "concepts" / ".iwh"
        nested = project / ".lexibrary" / ".lexibrary" / "concepts" / ".iwh"
        assert expected.exists(), f"expected .iwh at {expected}"
        assert not nested.exists(), f"should NOT have nested {nested}"


class TestDeprecationReport:
    """Report phase includes deprecation and migration counts."""

    def test_report_includes_deprecation_counts(self, tmp_path: Path) -> None:
        """Report includes deprecated and hard_deleted counts."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult()
        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="deprecation",
                        path=Path(".lexibrary/concepts/a.md"),
                        severity="warning",
                        message="test",
                        check="deprecation",
                    ),
                    issue_type="deprecation",
                    action_key="deprecate_concept",
                    priority=100.0,
                ),
                TriageItem(
                    source_item=CollectItem(
                        source="deprecation",
                        path=Path(".lexibrary/concepts/b.md"),
                        severity="warning",
                        message="test",
                        check="deprecation",
                    ),
                    issue_type="deprecation",
                    action_key="hard_delete_concept_past_ttl",
                    priority=20.0,
                ),
            ]
        )
        dispatch = DispatchResult(
            dispatched=[
                SubAgentResult(
                    success=True,
                    action_key="deprecate_concept",
                    path=Path(".lexibrary/concepts/a.md"),
                    message="Deprecated concept",
                    llm_calls=1,
                ),
                SubAgentResult(
                    success=True,
                    action_key="hard_delete_concept_past_ttl",
                    path=Path(".lexibrary/concepts/b.md"),
                    message="Hard-deleted concept",
                    llm_calls=0,
                ),
            ],
        )

        report = coord._report(
            collect,
            triage,
            dispatch,
            migrations_applied=1,
            migrations_proposed=2,
        )
        assert report.deprecated == 1
        assert report.hard_deleted == 1
        assert report.migrations_applied == 1
        assert report.migrations_proposed == 2
        assert report.fixed == 2

    def test_report_dry_run_no_deprecation_counts(self, tmp_path: Path) -> None:
        """Dry-run dispatches do not count as deprecated/hard_deleted."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult()
        triage = TriageResult(items=[])
        dispatch = DispatchResult(
            dispatched=[
                SubAgentResult(
                    success=True,
                    action_key="deprecate_concept",
                    path=Path(".lexibrary/concepts/a.md"),
                    message="dry-run: would dispatch",
                    llm_calls=0,
                    outcome="dry_run",
                ),
            ],
        )

        report = coord._report(collect, triage, dispatch)
        assert report.deprecated == 0
        assert report.hard_deleted == 0
        assert report.fixed == 0

    def test_report_json_includes_new_fields(self, tmp_path: Path) -> None:
        """JSON report file includes deprecation and migration fields."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult()
        triage = TriageResult(items=[])
        dispatch = DispatchResult(
            dispatched=[
                SubAgentResult(
                    success=True,
                    action_key="deprecate_concept",
                    path=Path(".lexibrary/concepts/a.md"),
                    message="Deprecated concept",
                    llm_calls=1,
                ),
            ],
        )

        report = coord._report(
            collect,
            triage,
            dispatch,
            migrations_applied=3,
            migrations_proposed=1,
        )
        assert report.report_path is not None
        data = json.loads(report.report_path.read_text(encoding="utf-8"))
        assert data["deprecated"] == 1
        assert data["hard_deleted"] == 0
        assert data["migrations_applied"] == 3
        assert data["migrations_proposed"] == 1


# ---------------------------------------------------------------------------
# Two-pass collect flow (Phase 5 — task 5.9)
# ---------------------------------------------------------------------------


class TestTwoPassFlow:
    """Two-pass collect flow honours hash-then-graph ordering and layer tags.

    Covers task 5.9 of the ``curator-freshness`` OpenSpec change:

    * Hash-pass regeneration is visible to the graph-pass collect so
      freshly-regenerated Dependencies do not trigger spurious
      ``bidirectional_deps`` issues in pass 2.
    * Every ``SubAgentResult`` emitted by ``_dispatch`` (and surfaced in
      ``CuratorReport.dispatched_details``) carries a ``layer`` key whose
      value is drawn from ``{"hash", "graph"}`` in the two-pass flow.
    * The legacy single-pass kill-switch (``two_pass_collect=False``)
      still emits ``schema_version=3``; the schema bump stands even when
      per-item ``layer`` may be absent / ``None`` on that path.
    * The 70/30 budget split caps hash-layer LLM spend at
      ``int(max_llm_calls_per_run * 0.7)`` while the shared counter
      leaves the remaining headroom for the graph layer.
    """

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_two_pass_end_to_end_hash_regen_visible_to_graph(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Pass-1 regenerates a stale design; pass-2 sees fresh deps.

        Seeds one design file with a stale source hash so hash-pass
        staleness collect fires ``regenerate_stale_design`` (via the
        real stub resolver).  ``validate_library`` is mocked so we can:

        * Observe the ``checks`` argument and confirm pass-1 receives
          ``_HASH_LAYER_CHECKS`` while pass-2 receives
          ``_GRAPH_LAYER_CHECKS``.
        * Record the design-file state at each call — the pass-2 call
          must see the regenerated file on disk (``updated_by=curator``
          and the fresh ``source_hash``), proving the hash-pass write
          is visible before graph-pass collect runs.
        * Return ZERO ``bidirectional_deps`` issues from pass-2, which
          is what the spec promises when the hash-pass fix cleared the
          underlying drift.
        """
        from lexibrary.curator.coordinator import (
            _GRAPH_LAYER_CHECKS,
            _HASH_LAYER_CHECKS,
        )

        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "# fresh\ndef bar(): pass\n")
        design_path = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_stale_hash",
            updated_by="archivist",
        )

        recorded_checks: list[frozenset[str]] = []
        design_snapshots: list[str] = []

        def validate_side_effect(
            project_root: Path,  # noqa: ARG001
            lexibrary_dir: Path,  # noqa: ARG001
            *,
            severity_filter: str | None = None,  # noqa: ARG001
            check_filter: str | None = None,  # noqa: ARG001
            checks: object | None = None,
        ) -> ValidationReport:
            checks_frozen = frozenset(checks) if checks is not None else frozenset()
            recorded_checks.append(checks_frozen)
            design_snapshots.append(design_path.read_text(encoding="utf-8"))
            # Pass-1 (hash layer): emit a hash_freshness issue so the
            # validation bridge fires a staleness-adjacent fix.  We also
            # rely on the real _collect_staleness path to add the
            # ``source="staleness"`` CollectItem that dispatches
            # ``regenerate_stale_design``; the validator side is
            # intentionally inert.
            #
            # Pass-2 (graph layer): return ZERO issues — in particular
            # no ``bidirectional_deps`` — because the stub resolver has
            # already rewritten the design with the current Dependencies.
            return ValidationReport(issues=[])

        with patch(
            "lexibrary.validator.validate_library",
            side_effect=validate_side_effect,
        ):
            config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
            coord = Coordinator(project, config)
            report = asyncio.run(coord.run())

        # Ordering: pass-1 sees hash-layer subset; pass-2 sees graph-layer.
        assert len(recorded_checks) == 2
        assert recorded_checks[0] == _HASH_LAYER_CHECKS
        assert recorded_checks[1] == _GRAPH_LAYER_CHECKS

        # Pass-2 must observe the regenerated design on disk (i.e. the
        # hash-pass dispatch completed before pass-2 collect ran).  The
        # stub resolver stamps ``updated_by: curator`` and rewrites the
        # file header, so the two snapshots must differ.
        assert design_snapshots[0] != design_snapshots[1]
        assert "updated_by: curator" in design_snapshots[1]

        # Pass-2 emitted no bidirectional_deps finding.  This is an
        # end-to-end assertion that graph-layer collect does not re-fire
        # stale-dep drift once hash-layer regeneration has landed.
        dispatched = list(report.dispatched_details)
        bidirectional_entries = [
            d for d in dispatched if d.get("action_key") == "fix_bidirectional_deps"
        ]
        assert not bidirectional_entries, (
            "Graph-pass emitted bidirectional_deps despite hash-pass "
            f"regeneration. Entries: {bidirectional_entries}"
        )

        # Pass-1 dispatched a staleness regen that succeeded.
        regen_entries = [
            d
            for d in dispatched
            if d.get("action_key") == "regenerate_stale_design" and d.get("outcome") == "fixed"
        ]
        assert regen_entries, (
            "Expected at least one regenerate_stale_design with outcome=fixed "
            f"in dispatched_details; got {dispatched}"
        )
        # Layer tagging lines up with the hash-pass origin.
        assert regen_entries[0].get("layer") == "hash"

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_dispatched_details_carry_layer_tag(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """``dispatched_details[*]['layer']`` is drawn from ``{"hash","graph"}``.

        Regression guard for task 5.1 / 5.9: the per-item layer field
        added to :class:`SubAgentResult` must survive triage and report
        serialisation.  Runs the full two-pass pipeline in ``dry_run``
        mode (so no real fixers are invoked) against fixtures that
        plant at least one hash-layer signal (stale design) and one
        graph-layer signal (mocked ``bidirectional_deps`` finding).
        Asserts every dispatched entry has a non-None ``layer`` and
        that both ``"hash"`` and ``"graph"`` are represented.
        """
        project = _setup_minimal_project(tmp_path)
        # Hash-layer signal: a stale design file drives the staleness
        # collector under _collect_hash_layer.
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        _make_design_file(
            project,
            "src/foo.py",
            source_hash="stale_hash_value",
            updated_by="archivist",
        )

        graph_layer_issue = ValidationIssue(
            severity="warning",
            check="bidirectional_deps",
            message="dependencies drift: missing src/bar.py",
            artifact="designs/src/foo.py.md",
        )

        def validate_side_effect(
            project_root: Path,  # noqa: ARG001
            lexibrary_dir: Path,  # noqa: ARG001
            *,
            severity_filter: str | None = None,  # noqa: ARG001
            check_filter: str | None = None,  # noqa: ARG001
            checks: object | None = None,
        ) -> ValidationReport:
            checks_frozen = frozenset(checks) if checks is not None else frozenset()
            # Only emit the graph-layer issue when called with the
            # graph-layer check set — the hash-layer pass should not
            # see bidirectional_deps.
            if "bidirectional_deps" in checks_frozen:
                return ValidationReport(issues=[graph_layer_issue])
            return ValidationReport(issues=[])

        with patch(
            "lexibrary.validator.validate_library",
            side_effect=validate_side_effect,
        ):
            config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
            coord = Coordinator(project, config)
            report = asyncio.run(coord.run(dry_run=True))

        dispatched = list(report.dispatched_details)
        assert dispatched, "Expected dry-run to produce dispatched entries"

        layers = {entry.get("layer") for entry in dispatched}
        # Every dispatched entry in a two-pass run must be tagged.
        assert None not in layers, (
            f"Two-pass dispatched_details contained a None layer: {dispatched}"
        )
        # The set of layer values must be a subset of the spec-legal
        # two-pass literals.
        assert layers.issubset({"hash", "graph"}), (
            f"Unexpected layer values: {layers}; dispatched_details={dispatched}"
        )
        # Both layers must be represented for this fixture (we planted
        # a hash-layer and a graph-layer signal).
        assert "hash" in layers
        assert "graph" in layers

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_legacy_flow_emits_schema_version_three(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Kill-switch (``two_pass_collect=False``) still emits schema v3.

        The schema bump from v2 to v3 stands even when the coordinator
        runs the legacy single-pass flow; only the per-item ``layer``
        field is permitted to be ``None`` on that path.  Confirms both
        the in-memory ``CuratorReport`` and the persisted JSON report
        carry ``schema_version == 3``.
        """
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        # Pin the source_hash so the legacy flow exits cleanly with
        # zero collect items — all we care about is the report shape.
        from lexibrary.ast_parser import compute_hashes  # noqa: PLC0415

        current_hash, _ = compute_hashes(project / "src/foo.py")
        _make_design_file(
            project,
            "src/foo.py",
            source_hash=current_hash,
            updated_by="archivist",
        )

        with patch("lexibrary.validator.validate_library") as mock_validate:
            mock_validate.return_value = ValidationReport(issues=[])

            config = LexibraryConfig.model_validate({"curator": {"two_pass_collect": False}})
            coord = Coordinator(project, config)
            report = asyncio.run(coord.run())

        assert report.schema_version == 3
        assert report.report_path is not None
        data = json.loads(report.report_path.read_text(encoding="utf-8"))
        assert data["schema_version"] == 3

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_budget_split_hash_capped_at_seven_graph_gets_three(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """70/30 split: hash-layer ≤ 7 LLM calls, graph-layer ≥ 3.

        Seeds >10 hash-layer signals (stale designs) and >10 graph-layer
        signals (mocked ``bidirectional_deps`` issues) then sets
        ``max_llm_calls_per_run=10``.  The shared-counter arithmetic
        implemented in task 5.5 guarantees:

        * ``hash_budget_cap = int(10 * 0.7) = 7``
        * ``graph_budget_cap = 10`` (clamped by shared counter)
        * ``pre_charged_llm_calls`` is bumped to the hash-pass total
          between passes, leaving ``10 - 7 = 3`` for the graph layer.

        ``_route_to_handler`` is monkeypatched to a cheap stand-in that
        records ``llm_calls=1`` per dispatch so the cap enforcement is
        deterministic.
        """
        project = _setup_minimal_project(tmp_path)

        # Plant 12 stale designs → hash-layer staleness collector emits
        # 12 CollectItems with layer="hash".
        for i in range(12):
            _make_source_file(project, f"src/mod{i}.py", f"def f{i}(): pass\n")
            _make_design_file(
                project,
                f"src/mod{i}.py",
                source_hash=f"stale_hash_{i}",
                updated_by="archivist",
            )

        # Plant >10 graph-layer validation issues.  Each maps to
        # ``fix_bidirectional_deps`` via ``CHECK_TO_ACTION_KEY``.
        graph_issues = [
            ValidationIssue(
                severity="warning",
                check="bidirectional_deps",
                message=f"dependencies drift: missing target_{i}",
                artifact=f"designs/src/mod{i}.py.md",
            )
            for i in range(12)
        ]

        def validate_side_effect(
            project_root: Path,  # noqa: ARG001
            lexibrary_dir: Path,  # noqa: ARG001
            *,
            severity_filter: str | None = None,  # noqa: ARG001
            check_filter: str | None = None,  # noqa: ARG001
            checks: object | None = None,
        ) -> ValidationReport:
            checks_frozen = frozenset(checks) if checks is not None else frozenset()
            if "bidirectional_deps" in checks_frozen:
                return ValidationReport(issues=list(graph_issues))
            return ValidationReport(issues=[])

        # Stand-in route handler: every dispatched item costs exactly
        # one LLM call so the 70/30 split translates directly to item
        # counts (7 hash, 3 graph).
        async def fake_route(
            self: Coordinator,  # noqa: ARG001
            item: TriageItem,
        ) -> SubAgentResult:
            return SubAgentResult(
                success=True,
                action_key=item.action_key,
                path=item.source_item.path,
                message="fake dispatch (budget-split test)",
                llm_calls=1,
                outcome="fixed",
            )

        monkeypatch.setattr(Coordinator, "_route_to_handler", fake_route)

        with patch(
            "lexibrary.validator.validate_library",
            side_effect=validate_side_effect,
        ):
            config = LexibraryConfig.model_validate(
                {
                    "curator": {
                        "autonomy": "full",
                        "max_llm_calls_per_run": 10,
                        # Disable consistency_collect so Low-risk
                        # collisions do not inflate graph-layer dispatch
                        # counts and obscure the budget accounting.
                        "consistency_collect": "off",
                    }
                }
            )
            coord = Coordinator(project, config)
            report = asyncio.run(coord.run())

        dispatched = list(report.dispatched_details)
        hash_dispatches = [d for d in dispatched if d.get("layer") == "hash"]
        graph_dispatches = [d for d in dispatched if d.get("layer") == "graph"]

        # Hash-layer cap: ``int(10 * 0.7) = 7`` LLM calls; each fake
        # dispatch is 1 LLM call, so at most 7 dispatched items.
        assert len(hash_dispatches) <= 7, (
            f"Hash-layer dispatched {len(hash_dispatches)} items, expected ≤ 7. "
            f"dispatched_details={dispatched}"
        )
        # Graph-layer must see at least 3 dispatches — the remaining
        # headroom after the hash pass consumed 7/10.
        assert len(graph_dispatches) >= 3, (
            f"Graph-layer dispatched only {len(graph_dispatches)} items, "
            f"expected ≥ 3. dispatched_details={dispatched}"
        )
        # Aggregate LLM consumption must not exceed the shared cap.
        assert len(hash_dispatches) + len(graph_dispatches) <= 10
