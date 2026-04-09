"""Tests for Phase 1.5b: Agent-Edit Reconciliation.

Covers: agent-edit detection via change_checker AGENT_UPDATED classification,
risk classification (Low/Medium/High), autonomy gating, reconciliation dispatch
with mocked BAML output, write contract enforcement, low-confidence IWH
creation, and integration with fixture variants.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import (
    parse_design_file_frontmatter,
    parse_design_file_metadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator, _design_body_length
from lexibrary.curator.models import (
    CollectItem,
    TriageItem,
    TriageResult,
)
from lexibrary.curator.reconciliation import (
    ReconciliationResult,
    ReconciliationWorkItem,
    _extract_section,
    _ReconciliationStubResult,
    reconcile_agent_design,
    reconciliation_result_to_sub_agent_result,
)
from lexibrary.utils.hashing import hash_file

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
    description: str = "Test design file",
    extra_body: str = "",
) -> Path:
    """Create a minimal design file matching a source path."""
    design_path = project_root / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=description,
            id=source_rel.replace("/", "-").replace(".", "-"),
            updated_by=updated_by,
            status="active",
        ),
        summary="Test summary" + extra_body,
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


def _make_agent_design_with_sections(
    project_root: Path,
    source_rel: str,
    *,
    source_hash: str = "abc123",
    interface_hash: str | None = None,
    dragons: str | None = None,
    key_concepts: str | None = None,
    insights: str | None = None,
) -> Path:
    """Create an agent-edited design file with preserved sections."""
    design_path = project_root / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    preserved = {}
    if dragons:
        preserved["Dragons"] = dragons
    if key_concepts:
        preserved["Key Concepts"] = key_concepts
    if insights:
        preserved["Insights"] = insights

    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Agent-edited design file",
            id=source_rel.replace("/", "-").replace(".", "-"),
            updated_by="agent",
            status="active",
        ),
        summary="Agent-written summary",
        interface_contract="def foo(): ...",
        dependencies=[],
        dependents=[],
        preserved_sections=preserved,
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=source_hash,
            interface_hash=interface_hash,
            generated=datetime.now(UTC),
            generator="agent",
        ),
    )
    content = serialize_design_file(df)
    design_path.write_text(content, encoding="utf-8")
    return design_path


def _setup_minimal_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with .lexibrary structure."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".lexibrary").mkdir()
    (project / ".lexibrary" / "designs").mkdir()
    (project / ".lexibrary" / "config.yaml").write_text("", encoding="utf-8")
    return project


def _run_coordinator(project: Path, **kwargs: object) -> object:
    """Convenience helper to run the coordinator synchronously."""
    config = LexibraryConfig()
    coord = Coordinator(project, config)
    return asyncio.run(coord.run(**kwargs))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Detection tests (12.1 / 12.5)
# ---------------------------------------------------------------------------


class TestAgentEditDetection:
    """Test that agent-edited files are detected via AGENT_UPDATED."""

    def test_agent_edited_stale_file_detected(self, tmp_path: Path) -> None:
        """Agent-edited file with stale source_hash is detected."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        _make_design_file(project, "src/foo.py", source_hash="old_hash", updated_by="agent")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        # Patch out validators and other collect steps to isolate staleness
        with (
            patch.object(coord, "_collect_validation"),
            patch.object(coord, "_collect_iwh"),
            patch.object(coord, "_collect_comments"),
            patch.object(coord, "_check_link_graph", return_value=False),
        ):
            result = coord._collect()

        staleness_items = [
            i for i in result.items if i.source == "staleness" and i.updated_by == "agent"
        ]
        assert len(staleness_items) >= 1
        assert staleness_items[0].source_hash_stale is True

    def test_agent_edited_current_hash_not_flagged(self, tmp_path: Path) -> None:
        """Agent-edited file with current source_hash is NOT flagged by staleness."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        current_hash = hash_file(source)
        _make_design_file(
            project,
            "src/foo.py",
            source_hash=current_hash,
            updated_by="agent",
        )

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        with (
            patch.object(coord, "_collect_validation"),
            patch.object(coord, "_collect_iwh"),
            patch.object(coord, "_collect_comments"),
            patch.object(coord, "_collect_agent_edits"),
            patch.object(coord, "_check_link_graph", return_value=False),
        ):
            result = coord._collect()

        stale_items = [
            i for i in result.items if i.source == "staleness" and i.updated_by == "agent"
        ]
        # Current hash means NOT stale
        assert len(stale_items) == 0

    def test_non_agent_stale_not_in_reconciliation(self, tmp_path: Path) -> None:
        """Non-agent stale file goes to staleness path, not reconciliation."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        _make_design_file(project, "src/foo.py", source_hash="old_hash", updated_by="archivist")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        with (
            patch.object(coord, "_collect_validation"),
            patch.object(coord, "_collect_iwh"),
            patch.object(coord, "_collect_comments"),
            patch.object(coord, "_check_link_graph", return_value=False),
        ):
            result = coord._collect()
            triage = coord._triage(result)

        reconciliation_items = [i for i in triage.items if i.issue_type == "reconciliation"]
        staleness_items = [i for i in triage.items if i.issue_type == "staleness"]
        assert len(reconciliation_items) == 0
        assert len(staleness_items) >= 1
        assert staleness_items[0].action_key == "regenerate_stale_design"


# ---------------------------------------------------------------------------
# Risk classification tests (12.2 / 12.5)
# ---------------------------------------------------------------------------


class TestRiskClassification:
    """Test the three-tier risk classification for reconciliation."""

    def test_stable_interface_classified_low(self) -> None:
        """Interface hash stable + small change -> Low risk."""
        risk, action = Coordinator._reconciliation_risk(
            interface_hash_stale=False,
            design_body_length=500,
        )
        assert risk == "low"
        assert action == "reconcile_agent_interface_stable"

    def test_changed_interface_classified_medium(self) -> None:
        """Interface hash changed -> Medium risk."""
        risk, action = Coordinator._reconciliation_risk(
            interface_hash_stale=True,
            design_body_length=500,
        )
        assert risk == "medium"
        assert action == "reconcile_agent_interface_changed"

    def test_extensive_content_classified_high(self) -> None:
        """Extensive agent content (body > 3000 chars) -> High risk."""
        risk, action = Coordinator._reconciliation_risk(
            interface_hash_stale=False,
            design_body_length=5000,
        )
        assert risk == "high"
        assert action == "reconcile_agent_extensive_content"

    def test_extensive_content_overrides_interface_change(self) -> None:
        """Extensive content takes precedence over interface change."""
        risk, action = Coordinator._reconciliation_risk(
            interface_hash_stale=True,
            design_body_length=5000,
        )
        assert risk == "high"
        assert action == "reconcile_agent_extensive_content"

    def test_triage_assigns_risk_level(self, tmp_path: Path) -> None:
        """Triage carries risk_level through to TriageItem."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        item = CollectItem(
            source="staleness",
            path=Path("src/foo.py"),
            severity="warning",
            message="stale",
            check="staleness",
            source_hash_stale=True,
            interface_hash_stale=True,
            updated_by="agent",
            design_body_length=100,
        )

        triage_item = coord._classify_staleness(item, graph_available=False)
        assert triage_item.risk_level == "medium"
        assert triage_item.action_key == "reconcile_agent_interface_changed"
        assert triage_item.issue_type == "reconciliation"

    def test_agent_edit_item_triage(self, tmp_path: Path) -> None:
        """Agent-edit collect items are triaged with correct risk level."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        item = CollectItem(
            source="agent_edit",
            path=Path("src/foo.py"),
            severity="warning",
            message="Agent-edited",
            check="agent_edit_detection",
            interface_hash_stale=False,
            design_body_length=200,
            agent_edit_reason="design_hash_drift",
        )

        triage_item = coord._classify_agent_edit(item, graph_available=False)
        assert triage_item.risk_level == "low"
        assert triage_item.issue_type == "reconciliation"
        assert triage_item.agent_edited is True


# ---------------------------------------------------------------------------
# Autonomy gating tests (12.5)
# ---------------------------------------------------------------------------


class TestAutonomyGating:
    """Test autonomy gating for reconciliation actions."""

    def test_auto_low_dispatches_low_risk(self, tmp_path: Path) -> None:
        """auto_low dispatches Low-risk reconciliation items."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        _make_design_file(project, "src/foo.py", source_hash="old", updated_by="agent")

        config = LexibraryConfig.model_validate({"curator": {"autonomy": "auto_low"}})
        coord = Coordinator(project, config)

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="staleness",
                        path=source,
                        severity="warning",
                        message="stale",
                        check="staleness",
                    ),
                    issue_type="reconciliation",
                    action_key="reconcile_agent_interface_stable",
                    priority=50.0,
                    agent_edited=True,
                    risk_level="low",
                ),
            ]
        )

        result = coord._dispatch(triage)
        assert len(result.dispatched) == 1
        assert len(result.deferred) == 0

    def test_auto_low_defers_medium_risk(self, tmp_path: Path) -> None:
        """auto_low defers Medium-risk reconciliation items."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate({"curator": {"autonomy": "auto_low"}})
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
                    issue_type="reconciliation",
                    action_key="reconcile_agent_interface_changed",
                    priority=100.0,
                    agent_edited=True,
                    risk_level="medium",
                ),
            ]
        )

        result = coord._dispatch(triage)
        assert len(result.dispatched) == 0
        assert len(result.deferred) == 1

    def test_auto_low_defers_high_risk(self, tmp_path: Path) -> None:
        """auto_low defers High-risk reconciliation items."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate({"curator": {"autonomy": "auto_low"}})
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
                    issue_type="reconciliation",
                    action_key="reconcile_agent_extensive_content",
                    priority=100.0,
                    agent_edited=True,
                    risk_level="high",
                ),
            ]
        )

        result = coord._dispatch(triage)
        assert len(result.dispatched) == 0
        assert len(result.deferred) == 1

    def test_full_dispatches_all(self, tmp_path: Path) -> None:
        """full autonomy dispatches all risk levels."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        _make_design_file(project, "src/foo.py", source_hash="old", updated_by="agent")

        config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
        coord = Coordinator(project, config)

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="staleness",
                        path=source,
                        severity="warning",
                        message="stale",
                        check="staleness",
                    ),
                    issue_type="reconciliation",
                    action_key="reconcile_agent_interface_changed",
                    priority=100.0,
                    agent_edited=True,
                    risk_level="medium",
                ),
            ]
        )

        result = coord._dispatch(triage)
        assert len(result.dispatched) == 1
        assert len(result.deferred) == 0

    def test_propose_defers_all(self, tmp_path: Path) -> None:
        """propose autonomy defers all reconciliation items."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig.model_validate({"curator": {"autonomy": "propose"}})
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
                    issue_type="reconciliation",
                    action_key="reconcile_agent_interface_stable",
                    priority=50.0,
                    agent_edited=True,
                    risk_level="low",
                ),
            ]
        )

        result = coord._dispatch(triage)
        assert len(result.dispatched) == 0
        assert len(result.deferred) == 1


# ---------------------------------------------------------------------------
# Reconciliation sub-agent unit tests (12.4 / 12.5)
# ---------------------------------------------------------------------------


class TestReconcileAgentDesign:
    """Test the reconcile_agent_design function."""

    def test_successful_reconciliation(self, tmp_path: Path) -> None:
        """Successful reconciliation writes the design file."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project, "src/foo.py", source_hash="old_hash", updated_by="agent"
        )

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=design,
            updated_by="agent",
        )
        result = reconcile_agent_design(work_item, project)

        assert result.success is True
        assert result.llm_calls == 1
        assert "Reconciled" in result.message

    def test_write_contract_updated_by_curator(self, tmp_path: Path) -> None:
        """Written file has updated_by=curator for reconciliations."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project, "src/foo.py", source_hash="old_hash", updated_by="agent"
        )

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=design,
            updated_by="agent",
        )
        reconcile_agent_design(work_item, project)

        fm = parse_design_file_frontmatter(design)
        assert fm is not None
        assert fm.updated_by == "curator"

    def test_write_contract_fresh_hashes(self, tmp_path: Path) -> None:
        """Written file has fresh source_hash and interface_hash."""
        project = _setup_minimal_project(tmp_path)
        source_content = "def foo(): pass\n"
        source = _make_source_file(project, "src/foo.py", source_content)
        design = _make_design_file(
            project, "src/foo.py", source_hash="old_hash", updated_by="agent"
        )

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=design,
            updated_by="agent",
        )
        reconcile_agent_design(work_item, project)

        metadata = parse_design_file_metadata(design)
        assert metadata is not None
        expected_hash = hash_file(source)
        assert metadata.source_hash == expected_hash

    def test_write_contract_design_hash_present(self, tmp_path: Path) -> None:
        """Written file has a design_hash computed by the serializer."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project, "src/foo.py", source_hash="old_hash", updated_by="agent"
        )

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=design,
            updated_by="agent",
        )
        reconcile_agent_design(work_item, project)

        metadata = parse_design_file_metadata(design)
        assert metadata is not None
        assert metadata.design_hash is not None
        assert len(metadata.design_hash) == 64  # SHA-256 hex

    def test_preserves_agent_sections(self, tmp_path: Path) -> None:
        """Reconciliation preserves agent-authored sections (Dragons, Insights)."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_agent_design_with_sections(
            project,
            "src/foo.py",
            source_hash="old_hash",
            dragons="Beware the null pointer!",
            insights="This function is performance-critical.",
        )

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=design,
            updated_by="agent",
        )
        reconcile_agent_design(work_item, project)

        # Read the written file and check preserved sections
        content = design.read_text(encoding="utf-8")
        assert "Beware the null pointer!" in content
        assert "This function is performance-critical." in content

    def test_source_file_missing_fails(self, tmp_path: Path) -> None:
        """Missing source file returns failure."""
        project = _setup_minimal_project(tmp_path)
        design = _make_design_file(project, "src/foo.py", source_hash="old", updated_by="agent")

        work_item = ReconciliationWorkItem(
            source_path=project / "src/foo.py",  # does not exist
            design_path=design,
            updated_by="agent",
        )
        result = reconcile_agent_design(work_item, project)

        assert result.success is False
        assert "Failed to read source" in result.message

    def test_design_file_missing_fails(self, tmp_path: Path) -> None:
        """Missing design file returns failure."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=project / ".lexibrary" / "designs" / "src" / "foo.py.md",
            updated_by="agent",
        )
        result = reconcile_agent_design(work_item, project)

        assert result.success is False
        assert "Failed to read agent-edited design" in result.message


class TestLowConfidenceHandling:
    """Test low-confidence reconciliation output handling."""

    def test_low_confidence_discarded_iwh_written(self, tmp_path: Path) -> None:
        """Low-confidence output is discarded and IWH signal is written."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project, "src/foo.py", source_hash="old_hash", updated_by="agent"
        )

        # Save original design content
        original_content = design.read_text(encoding="utf-8")

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=design,
            updated_by="agent",
        )

        # Mock the stub to return low confidence
        low_conf_result = _ReconciliationStubResult(
            success=True,
            summary="stubbed",
            interface_contract="stubbed",
            confidence=0.3,
            recommendation="human_review",
            llm_calls=1,
        )

        with patch(
            "lexibrary.curator.reconciliation._reconciliation_stub",
            return_value=low_conf_result,
        ):
            result = reconcile_agent_design(work_item, project)

        assert result.success is False
        assert result.low_confidence is True
        assert result.iwh_written is True

        # Design file should be unchanged (not overwritten)
        assert design.read_text(encoding="utf-8") == original_content

        # IWH signal should exist in the design file's directory
        iwh_path = design.parent / ".iwh"
        assert iwh_path.exists()
        iwh_content = iwh_path.read_text(encoding="utf-8")
        assert "low-confidence" in iwh_content.lower() or "warning" in iwh_content.lower()

    def test_full_regen_recommendation_deferred(self, tmp_path: Path) -> None:
        """full_regen recommendation is treated as deferred."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project, "src/foo.py", source_hash="old_hash", updated_by="agent"
        )

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=design,
            updated_by="agent",
        )

        regen_result = _ReconciliationStubResult(
            success=True,
            summary="stubbed",
            interface_contract="stubbed",
            confidence=0.9,
            recommendation="full_regen",
            llm_calls=1,
        )

        with patch(
            "lexibrary.curator.reconciliation._reconciliation_stub",
            return_value=regen_result,
        ):
            result = reconcile_agent_design(work_item, project)

        assert result.success is False
        assert result.deferred is True
        assert "full regeneration" in result.message


class TestReconciliationStubResult:
    """Test the BAML stub result conversion."""

    def test_result_to_sub_agent_result(self, tmp_path: Path) -> None:
        """ReconciliationResult converts correctly to SubAgentResult."""
        project = _setup_minimal_project(tmp_path)

        result = ReconciliationResult(
            success=True,
            source_path=project / "src/foo.py",
            design_path=project / ".lexibrary/designs/src/foo.py.md",
            message="Reconciled",
            llm_calls=1,
        )

        sub = reconciliation_result_to_sub_agent_result(result)
        assert sub.success is True
        assert sub.llm_calls == 1
        assert sub.action_key == "reconcile_agent_interface_stable"

    def test_low_confidence_result_action_key(self, tmp_path: Path) -> None:
        """Low-confidence result gets flag_unresolvable action key."""
        project = _setup_minimal_project(tmp_path)

        result = ReconciliationResult(
            success=False,
            source_path=project / "src/foo.py",
            design_path=project / ".lexibrary/designs/src/foo.py.md",
            message="Low confidence",
            llm_calls=1,
            low_confidence=True,
        )

        sub = reconciliation_result_to_sub_agent_result(result)
        assert sub.action_key == "flag_unresolvable_agent_design"


# ---------------------------------------------------------------------------
# Section extraction tests
# ---------------------------------------------------------------------------


class TestExtractSection:
    """Test the _extract_section helper used by the stub."""

    def test_extracts_dragons_section(self) -> None:
        content = (
            "## Summary\n\nSome summary.\n\n## Dragons\n\nHere be dragons!\n\n## Tags\n\ntag1\n"
        )
        result = _extract_section(content, "Dragons")
        assert result == "Here be dragons!"

    def test_returns_none_for_missing_section(self) -> None:
        content = "## Summary\n\nSome summary.\n"
        result = _extract_section(content, "Dragons")
        assert result is None

    def test_returns_none_for_empty_section(self) -> None:
        content = "## Dragons\n\n## Tags\n\ntag1\n"
        result = _extract_section(content, "Dragons")
        assert result is None

    def test_extracts_last_section(self) -> None:
        content = "## Summary\n\nSome summary.\n\n## Insights\n\nImportant insight!\n"
        result = _extract_section(content, "Insights")
        assert result == "Important insight!"


# ---------------------------------------------------------------------------
# Design body length helper tests
# ---------------------------------------------------------------------------


class TestDesignBodyLength:
    """Test the _design_body_length helper."""

    def test_normal_design_file(self, tmp_path: Path) -> None:
        """Computes body length excluding frontmatter and footer."""
        design = tmp_path / "test.md"
        design.write_text(
            "---\ndescription: test\n---\n\n# File\n\nBody content.\n\n"
            "<!-- lexibrary:meta\nsource: foo\n-->\n",
            encoding="utf-8",
        )
        length = _design_body_length(design)
        assert 0 < length < 100

    def test_missing_file(self, tmp_path: Path) -> None:
        """Returns 0 for missing file."""
        assert _design_body_length(tmp_path / "nonexistent.md") == 0

    def test_extensive_content(self, tmp_path: Path) -> None:
        """Long body produces high character count."""
        design = tmp_path / "test.md"
        long_body = "x" * 5000
        design.write_text(
            f"---\ndescription: test\n---\n\n{long_body}\n\n"
            "<!-- lexibrary:meta\nsource: foo\n-->\n",
            encoding="utf-8",
        )
        length = _design_body_length(design)
        assert length > 3000


# ---------------------------------------------------------------------------
# Integration: fixture variant tests (12.5)
# ---------------------------------------------------------------------------


class TestReconciliationFixtureVariants:
    """Integration tests with different fixture variants."""

    def test_small_divergence(self, tmp_path: Path) -> None:
        """Small divergence: agent made minor edits, reconciles successfully."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(
            project, "src/foo.py", "def foo(x: int) -> int:\n    return x + 1\n"
        )
        _make_agent_design_with_sections(
            project,
            "src/foo.py",
            source_hash="old_hash",
            dragons="Watch out for negative inputs!",
        )

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=project / ".lexibrary" / "designs" / "src" / "foo.py.md",
            updated_by="agent",
            risk_level="low",
        )
        result = reconcile_agent_design(work_item, project)

        assert result.success is True
        # Verify dragon content preserved
        content = work_item.design_path.read_text(encoding="utf-8")
        assert "Watch out for negative inputs!" in content

    def test_large_divergence(self, tmp_path: Path) -> None:
        """Large divergence: interface changed, reconciles with medium risk."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(
            project,
            "src/foo.py",
            "class Foo:\n    def bar(self) -> str:\n        return 'hello'\n",
        )
        design = _make_agent_design_with_sections(
            project,
            "src/foo.py",
            source_hash="old_hash",
            interface_hash="old_interface",
            key_concepts="This uses the factory pattern.",
            dragons="Thread safety not guaranteed.",
        )

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=design,
            updated_by="agent",
            risk_level="medium",
        )
        result = reconcile_agent_design(work_item, project)

        assert result.success is True
        content = design.read_text(encoding="utf-8")
        assert "Thread safety not guaranteed." in content

    def test_extensive_content(self, tmp_path: Path) -> None:
        """Extensive content: very long agent body, reconciles with high risk."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")

        # Create design with extensive content
        long_dragons = "Important knowledge: " + ("x" * 4000)
        _make_agent_design_with_sections(
            project,
            "src/foo.py",
            source_hash="old_hash",
            dragons=long_dragons,
        )

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=project / ".lexibrary" / "designs" / "src" / "foo.py.md",
            updated_by="agent",
            risk_level="high",
        )
        result = reconcile_agent_design(work_item, project)

        assert result.success is True
        content = work_item.design_path.read_text(encoding="utf-8")
        assert "Important knowledge:" in content


class TestFallbackBehavior:
    """Test fallback/error handling in reconciliation."""

    def test_malformed_stub_output_discarded(self, tmp_path: Path) -> None:
        """Malformed BAML output results in failure, file untouched."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project, "src/foo.py", source_hash="old_hash", updated_by="agent"
        )
        original_content = design.read_text(encoding="utf-8")

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=design,
            updated_by="agent",
        )

        # Mock stub returning failure
        failed_result = _ReconciliationStubResult(
            success=False,
            message="BAML parse error: malformed output",
            llm_calls=1,
        )

        with patch(
            "lexibrary.curator.reconciliation._reconciliation_stub",
            return_value=failed_result,
        ):
            result = reconcile_agent_design(work_item, project)

        assert result.success is False
        assert "BAML reconciliation failed" in result.message
        # File should be unchanged
        assert design.read_text(encoding="utf-8") == original_content

    def test_timeout_returns_failure(self, tmp_path: Path) -> None:
        """Exception during reconciliation returns failure for retry."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project, "src/foo.py", source_hash="old_hash", updated_by="agent"
        )

        work_item = ReconciliationWorkItem(
            source_path=source,
            design_path=design,
            updated_by="agent",
        )

        with (
            patch(
                "lexibrary.curator.reconciliation._reconciliation_stub",
                side_effect=TimeoutError("BAML call timed out"),
            ),
            pytest.raises(TimeoutError),
        ):
            reconcile_agent_design(work_item, project)


# ---------------------------------------------------------------------------
# Coordinator integration tests
# ---------------------------------------------------------------------------


class TestCoordinatorReconciliationIntegration:
    """Integration tests for reconciliation through the full coordinator pipeline."""

    def test_agent_stale_file_reconciled_via_coordinator(self, tmp_path: Path) -> None:
        """Agent-edited stale file is detected, triaged, and dispatched for reconciliation."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        _make_design_file(project, "src/foo.py", source_hash="old_hash", updated_by="agent")

        config = LexibraryConfig.model_validate({"curator": {"autonomy": "auto_low"}})
        coord = Coordinator(project, config)

        # Patch out validation, IWH, comments, and link graph
        with (
            patch.object(coord, "_collect_validation"),
            patch.object(coord, "_collect_iwh"),
            patch.object(coord, "_collect_comments"),
            patch.object(coord, "_check_link_graph", return_value=False),
        ):
            collect_result = coord._collect()
            triage_result = coord._triage(collect_result)
            dispatch_result = coord._dispatch(triage_result)

        # The agent-edited file should be detected and dispatched
        reconciliation_dispatched = [
            d
            for d in dispatch_result.dispatched
            if "reconcile" in d.action_key or "flag" in d.action_key
        ]
        assert len(reconciliation_dispatched) >= 1

    def test_full_pipeline_with_reconciliation(self, tmp_path: Path) -> None:
        """Full pipeline run with agent-edited file produces a valid report."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        _make_design_file(project, "src/foo.py", source_hash="old_hash", updated_by="agent")

        config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
        coord = Coordinator(project, config)

        # Patch validation to avoid needing full library setup
        with (
            patch.object(coord, "_collect_validation"),
            patch.object(coord, "_collect_iwh"),
            patch.object(coord, "_collect_comments"),
            patch.object(coord, "_check_link_graph", return_value=False),
        ):
            report = asyncio.run(coord.run())

        assert report.checked >= 1
        assert report.errored == 0
