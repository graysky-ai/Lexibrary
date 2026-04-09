"""Tests for Phase 1a: Validation + Hash Staleness.

Covers the staleness resolver, its integration with the coordinator,
validation wiring, triage priority ranking, and the design file write
contract.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

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
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.models import (
    CollectItem,
    CollectResult,
    CuratorReport,
    TriageItem,
    TriageResult,
)
from lexibrary.curator.staleness import (
    StalenessResult,
    StalenessWorkItem,
    is_agent_edited,
    resolve_stale_design,
    staleness_result_to_sub_agent_result,
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
# Staleness Resolver unit tests
# ---------------------------------------------------------------------------


class TestIsAgentEdited:
    """Test the is_agent_edited helper."""

    def test_agent_is_agent_edited(self) -> None:
        assert is_agent_edited("agent") is True

    def test_maintainer_is_agent_edited(self) -> None:
        assert is_agent_edited("maintainer") is True

    def test_archivist_not_agent_edited(self) -> None:
        assert is_agent_edited("archivist") is False

    def test_curator_not_agent_edited(self) -> None:
        assert is_agent_edited("curator") is False

    def test_bootstrap_quick_not_agent_edited(self) -> None:
        assert is_agent_edited("bootstrap-quick") is False

    def test_skeleton_fallback_not_agent_edited(self) -> None:
        assert is_agent_edited("skeleton-fallback") is False


class TestResolveStaleDesign:
    """Test the resolve_stale_design function."""

    def test_agent_edited_file_deferred(self, tmp_path: Path) -> None:
        """Agent-edited files are deferred, not resolved."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "# content\n")
        design = _make_design_file(project, "src/foo.py", updated_by="agent")

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="agent",
        )
        result = resolve_stale_design(work_item, project)

        assert result.success is False
        assert result.deferred is True
        assert "Deferred" in result.message
        assert "agent" in result.message

    def test_maintainer_edited_file_deferred(self, tmp_path: Path) -> None:
        """Maintainer-edited files are also deferred."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "# content\n")
        design = _make_design_file(project, "src/foo.py", updated_by="maintainer")

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="maintainer",
        )
        result = resolve_stale_design(work_item, project)

        assert result.success is False
        assert result.deferred is True

    def test_archivist_file_regenerated(self, tmp_path: Path) -> None:
        """Non-agent files are fully regenerated."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "# updated content\ndef bar(): pass\n")
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="archivist",
        )
        result = resolve_stale_design(work_item, project)

        assert result.success is True
        assert result.deferred is False
        assert result.llm_calls == 1
        assert "Regenerated" in result.message

    def test_bootstrap_quick_file_regenerated(self, tmp_path: Path) -> None:
        """bootstrap-quick files treated as non-agent and regenerated."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "# content\n")
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="bootstrap-quick",
        )

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="bootstrap-quick",
        )
        result = resolve_stale_design(work_item, project)
        assert result.success is True

    def test_skeleton_fallback_file_regenerated(self, tmp_path: Path) -> None:
        """skeleton-fallback files treated as non-agent and regenerated."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "# content\n")
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="skeleton-fallback",
        )

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="skeleton-fallback",
        )
        result = resolve_stale_design(work_item, project)
        assert result.success is True

    def test_write_contract_updated_by_archivist(self, tmp_path: Path) -> None:
        """Written file has updated_by=archivist."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="archivist",
        )
        resolve_stale_design(work_item, project)

        # Verify the written file
        fm = parse_design_file_frontmatter(design)
        assert fm is not None
        assert fm.updated_by == "archivist"

    def test_write_contract_fresh_hashes(self, tmp_path: Path) -> None:
        """Written file has fresh source_hash and interface_hash."""
        project = _setup_minimal_project(tmp_path)
        source_content = "def foo(): pass\n"
        source = _make_source_file(project, "src/foo.py", source_content)
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="archivist",
        )
        resolve_stale_design(work_item, project)

        # Verify hashes are fresh
        metadata = parse_design_file_metadata(design)
        assert metadata is not None
        expected_hash = hash_file(source)
        assert metadata.source_hash == expected_hash

    def test_write_contract_design_hash_present(self, tmp_path: Path) -> None:
        """Written file has a design_hash computed by the serializer."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="archivist",
        )
        resolve_stale_design(work_item, project)

        metadata = parse_design_file_metadata(design)
        assert metadata is not None
        assert metadata.design_hash is not None
        assert len(metadata.design_hash) == 64  # SHA-256 hex

    def test_write_contract_atomic_write_used(self, tmp_path: Path) -> None:
        """Verify atomic_write is called (not direct file write)."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="archivist",
        )

        with patch("lexibrary.curator.staleness.atomic_write") as mock_write:
            resolve_stale_design(work_item, project)
            mock_write.assert_called_once()
            # Verify the target path and content
            call_args = mock_write.call_args
            assert call_args[0][0] == design  # target path
            assert isinstance(call_args[0][1], str)  # content string

    def test_write_contract_serialize_design_file_used(self, tmp_path: Path) -> None:
        """Verify output passes through serialize_design_file."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="archivist",
        )

        with patch(
            "lexibrary.curator.staleness.serialize_design_file",
            wraps=serialize_design_file,
        ) as mock_serialize:
            resolve_stale_design(work_item, project)
            mock_serialize.assert_called_once()

    def test_missing_source_file_fails(self, tmp_path: Path) -> None:
        """Resolver fails gracefully when source file doesn't exist."""
        project = _setup_minimal_project(tmp_path)
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        work_item = StalenessWorkItem(
            source_path=project / "src" / "foo.py",
            design_path=design,
            updated_by="archivist",
        )
        result = resolve_stale_design(work_item, project)
        assert result.success is False
        assert "Failed to read source" in result.message

    def test_generator_set_to_curator_staleness_resolver(self, tmp_path: Path) -> None:
        """Written file has generator=curator-staleness-resolver."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="archivist",
        )
        resolve_stale_design(work_item, project)

        metadata = parse_design_file_metadata(design)
        assert metadata is not None
        assert metadata.generator == "curator-staleness-resolver"

    def test_preserves_existing_design_id(self, tmp_path: Path) -> None:
        """Resolver preserves the existing design file's ID."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
            description="Original description",
        )

        # Read the original ID
        orig_fm = parse_design_file_frontmatter(design)
        assert orig_fm is not None
        orig_id = orig_fm.id

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design,
            updated_by="archivist",
        )
        resolve_stale_design(work_item, project)

        new_fm = parse_design_file_frontmatter(design)
        assert new_fm is not None
        assert new_fm.id == orig_id

    def test_preserves_preserved_sections(self, tmp_path: Path) -> None:
        """Resolver preserves the Insights section from existing design."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "def foo(): pass\n")

        # Create a design file with a preserved section
        design_path = project / ".lexibrary" / "designs" / "src" / "foo.py.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        df = DesignFile(
            source_path="src/foo.py",
            frontmatter=DesignFileFrontmatter(
                description="Test",
                id="src-foo-py",
                updated_by="archivist",
                status="active",
            ),
            summary="Test summary",
            interface_contract="def foo(): ...",
            dependencies=[],
            dependents=[],
            preserved_sections={"Insights": "This function has a subtle edge case."},
            metadata=StalenessMetadata(
                source="src/foo.py",
                source_hash="old_hash",
                interface_hash=None,
                generated=datetime.now(UTC),
                generator="test",
            ),
        )
        content = serialize_design_file(df)
        design_path.write_text(content, encoding="utf-8")

        work_item = StalenessWorkItem(
            source_path=source,
            design_path=design_path,
            updated_by="archivist",
        )
        resolve_stale_design(work_item, project)

        # Read back and verify Insights preserved
        result_content = design_path.read_text(encoding="utf-8")
        assert "## Insights" in result_content
        assert "subtle edge case" in result_content


class TestStalenessResultConversion:
    """Test staleness_result_to_sub_agent_result conversion."""

    def test_successful_result(self) -> None:
        result = StalenessResult(
            success=True,
            source_path=Path("src/foo.py"),
            design_path=Path(".lexibrary/designs/src/foo.py.md"),
            message="Regenerated",
            llm_calls=1,
        )
        sub = staleness_result_to_sub_agent_result(result)
        assert sub.success is True
        assert sub.action_key == "regenerate_stale_design"
        assert sub.llm_calls == 1

    def test_failed_result(self) -> None:
        result = StalenessResult(
            success=False,
            source_path=Path("src/foo.py"),
            design_path=Path(".lexibrary/designs/src/foo.py.md"),
            message="Failed",
        )
        sub = staleness_result_to_sub_agent_result(result)
        assert sub.success is False


# ---------------------------------------------------------------------------
# Triage: validation + staleness ranking
# ---------------------------------------------------------------------------


class TestTriageValidation:
    """Mixed-severity ValidationReport triaged correctly."""

    def test_mixed_severity_triage(self, tmp_path: Path) -> None:
        """Error-severity items rank higher than warning and info."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="validation",
                    path=Path("some/artifact"),
                    severity="info",
                    message="informational issue",
                    check="info_check",
                ),
                CollectItem(
                    source="validation",
                    path=Path("some/artifact"),
                    severity="error",
                    message="critical issue",
                    check="error_check",
                ),
                CollectItem(
                    source="validation",
                    path=Path("some/artifact"),
                    severity="warning",
                    message="warning issue",
                    check="warning_check",
                ),
            ]
        )

        result = coord._triage(collect)
        assert len(result.items) == 3
        # Sorted by priority descending: error > warning > info
        assert result.items[0].source_item.severity == "error"
        assert result.items[1].source_item.severity == "warning"
        assert result.items[2].source_item.severity == "info"

    def test_validation_issues_classified_as_consistency(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="validation",
                    path=Path("some/artifact"),
                    severity="error",
                    message="broken wikilink",
                    check="wikilink_resolution",
                ),
            ]
        )

        result = coord._triage(collect)
        assert len(result.items) == 1
        assert result.items[0].issue_type == "consistency"


class TestTriageStalenessRanking:
    """Hash-based staleness ranking in triage."""

    def test_stale_source_hash_stable_interface_lower_priority(self, tmp_path: Path) -> None:
        """Content-only change (source stale, interface ok) = lower priority."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="staleness",
                    path=Path("src/foo.py"),
                    severity="info",
                    message="stale",
                    check="staleness",
                    source_hash_stale=True,
                    interface_hash_stale=False,
                    updated_by="archivist",
                ),
            ]
        )

        result = coord._triage(collect)
        assert len(result.items) == 1
        # Source-only: 50.0 priority
        assert result.items[0].priority == pytest.approx(50.0)

    def test_stale_interface_hash_higher_priority(self, tmp_path: Path) -> None:
        """Interface hash change = higher priority than content-only."""
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
        # Interface-stale item should be first (higher priority)
        assert result.items[0].source_item.path == Path("src/high.py")
        assert result.items[0].priority > result.items[1].priority

    def test_non_agent_file_gets_regenerate_action(self, tmp_path: Path) -> None:
        """Non-agent files get regenerate_stale_design action key."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="staleness",
                    path=Path("src/foo.py"),
                    severity="info",
                    message="stale",
                    check="staleness",
                    source_hash_stale=True,
                    updated_by="archivist",
                ),
            ]
        )

        result = coord._triage(collect)
        assert result.items[0].action_key == "regenerate_stale_design"
        assert result.items[0].agent_edited is False

    def test_agent_file_gets_reconcile_action(self, tmp_path: Path) -> None:
        """Agent-edited files get reconcile action key."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            items=[
                CollectItem(
                    source="staleness",
                    path=Path("src/foo.py"),
                    severity="info",
                    message="stale",
                    check="staleness",
                    source_hash_stale=True,
                    interface_hash_stale=False,
                    updated_by="agent",
                ),
            ]
        )

        result = coord._triage(collect)
        assert result.items[0].action_key == "reconcile_agent_interface_stable"
        assert result.items[0].agent_edited is True

    def test_staleness_ranking_by_reverse_deps(self, tmp_path: Path) -> None:
        """Items with more reverse dependents get higher priority."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = CollectResult(
            link_graph_available=True,
            items=[
                CollectItem(
                    source="staleness",
                    path=Path("src/low_deps.py"),
                    severity="info",
                    message="stale",
                    check="staleness",
                    source_hash_stale=True,
                    updated_by="archivist",
                ),
                CollectItem(
                    source="staleness",
                    path=Path("src/high_deps.py"),
                    severity="info",
                    message="stale",
                    check="staleness",
                    source_hash_stale=True,
                    updated_by="archivist",
                ),
            ],
        )

        # Mock reverse dep counts
        def mock_get_reverse_dep_count(path: Path) -> int:
            if "high_deps" in str(path):
                return 10
            return 1

        with patch.object(coord, "_get_reverse_dep_count", side_effect=mock_get_reverse_dep_count):
            result = coord._triage(collect)

        assert len(result.items) == 2
        # high_deps has 10 * 5.0 = 50 more priority
        assert result.items[0].source_item.path == Path("src/high_deps.py")
        assert result.items[0].reverse_dep_count == 10


# ---------------------------------------------------------------------------
# Coordinator dispatch: staleness resolver integration
# ---------------------------------------------------------------------------


class TestDispatchStalenessResolver:
    """Coordinator dispatches stale non-agent files to the resolver."""

    @pytest.mark.asyncio
    async def test_non_agent_file_dispatched_to_resolver(self, tmp_path: Path) -> None:
        """Non-agent stale file is dispatched through the staleness resolver."""
        project = _setup_minimal_project(tmp_path)
        source = _make_source_file(project, "src/foo.py", "# updated\ndef bar(): pass\n")
        _make_design_file(project, "src/foo.py", source_hash="old_hash", updated_by="archivist")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        triage = TriageResult(
            items=[
                TriageItem(
                    source_item=CollectItem(
                        source="staleness",
                        path=source,
                        severity="info",
                        message="stale",
                        check="staleness",
                        source_hash_stale=True,
                        updated_by="archivist",
                    ),
                    issue_type="staleness",
                    action_key="regenerate_stale_design",
                    priority=50.0,
                ),
            ]
        )

        result = await coord._dispatch(triage)
        assert len(result.dispatched) == 1
        assert result.dispatched[0].success is True
        assert result.dispatched[0].action_key == "regenerate_stale_design"
        assert result.dispatched[0].llm_calls == 1

    @pytest.mark.asyncio
    async def test_agent_file_deferred_not_dispatched(self, tmp_path: Path) -> None:
        """Agent-edited files are deferred by autonomy gating (medium risk)."""
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()  # default autonomy = auto_low
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
                        source_hash_stale=True,
                        interface_hash_stale=True,
                        updated_by="agent",
                    ),
                    issue_type="staleness",
                    action_key="reconcile_agent_interface_changed",
                    priority=150.0,
                    agent_edited=True,
                ),
            ]
        )

        result = await coord._dispatch(triage)
        # reconcile_agent_interface_changed is Medium risk, auto_low defers it
        assert len(result.dispatched) == 0
        assert len(result.deferred) == 1


# ---------------------------------------------------------------------------
# Integration tests: full coordinator run
# ---------------------------------------------------------------------------


class TestPhase1aIntegration:
    """End-to-end integration tests for Phase 1a."""

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_stale_non_agent_file_regenerated(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A stale archivist-authored design file is regenerated."""
        project = _setup_minimal_project(tmp_path)
        source_content = "# updated\ndef bar(): pass\n"
        source = _make_source_file(project, "src/foo.py", source_content)
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        with patch("lexibrary.validator.validate_library") as mock_validate:
            from lexibrary.validator.report import ValidationReport

            mock_validate.return_value = ValidationReport(issues=[])
            report = _run_coordinator(project)

        assert report.fixed >= 1
        assert "regenerate_stale_design" in report.sub_agent_calls

        # Verify the design file was rewritten with fresh hashes
        metadata = parse_design_file_metadata(design)
        assert metadata is not None
        expected_hash = hash_file(source)
        assert metadata.source_hash == expected_hash

        fm = parse_design_file_frontmatter(design)
        assert fm is not None
        assert fm.updated_by == "archivist"

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_agent_file_not_regenerated(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A stale agent-edited file is NOT dispatched to the staleness
        resolver.  It gets a reconciliation action key instead."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "# updated\n")
        _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="agent",
        )

        with patch("lexibrary.validator.validate_library") as mock_validate:
            from lexibrary.validator.report import ValidationReport

            mock_validate.return_value = ValidationReport(issues=[])
            report = _run_coordinator(project)

        # Agent file should NOT be dispatched to the staleness resolver
        assert "regenerate_stale_design" not in report.sub_agent_calls
        # It should go through the reconciliation path (stub for now)
        assert "reconcile_agent_interface_stable" in report.sub_agent_calls

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_agent_file_interface_changed_deferred_auto_low(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Agent file with changed interface is deferred under auto_low
        because reconcile_agent_interface_changed is Medium risk."""
        project = _setup_minimal_project(tmp_path)
        source_content = "# updated\ndef new_api(): pass\n"
        _make_source_file(project, "src/foo.py", source_content)
        _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            interface_hash="old_iface_hash",
            updated_by="agent",
        )

        with patch("lexibrary.validator.validate_library") as mock_validate:
            from lexibrary.validator.report import ValidationReport

            mock_validate.return_value = ValidationReport(issues=[])
            report = _run_coordinator(project)

        # reconcile_agent_interface_changed is Medium risk, deferred under auto_low
        assert report.deferred >= 1
        assert "regenerate_stale_design" not in report.sub_agent_calls

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_healthy_file_untouched(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """A healthy design file with current hashes is not touched."""
        project = _setup_minimal_project(tmp_path)
        source_content = "def foo(): pass\n"
        source = _make_source_file(project, "src/foo.py", source_content)
        current_hash = hash_file(source)
        _make_design_file(
            project,
            "src/foo.py",
            source_hash=current_hash,
            updated_by="archivist",
        )

        with patch("lexibrary.validator.validate_library") as mock_validate:
            from lexibrary.validator.report import ValidationReport

            mock_validate.return_value = ValidationReport(issues=[])
            report = _run_coordinator(project)

        # No staleness items should be dispatched
        assert report.fixed == 0
        assert "regenerate_stale_design" not in report.sub_agent_calls

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_max_llm_calls_respected(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """max_llm_calls_per_run is respected -- excess items deferred."""
        project = _setup_minimal_project(tmp_path)
        # Create 3 stale files
        for i in range(3):
            _make_source_file(project, f"src/file{i}.py", f"# content {i}\n")
            _make_design_file(
                project,
                f"src/file{i}.py",
                source_hash="old_hash",
                updated_by="archivist",
            )

        # Limit to 1 LLM call
        config = LexibraryConfig.model_validate({"curator": {"max_llm_calls_per_run": 1}})
        coord = Coordinator(project, config)

        with patch("lexibrary.validator.validate_library") as mock_validate:
            from lexibrary.validator.report import ValidationReport

            mock_validate.return_value = ValidationReport(issues=[])
            report = asyncio.run(coord.run())

        # Only 1 should be fixed, the rest deferred due to LLM cap
        assert report.fixed == 1
        assert report.deferred >= 2
        assert report.sub_agent_calls.get("regenerate_stale_design", 0) == 1

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_dry_run_reports_counts_no_modification(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """dry_run reports counts but doesn't modify files."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "# updated\ndef bar(): pass\n")
        design = _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        original_content = design.read_text(encoding="utf-8")

        with patch("lexibrary.validator.validate_library") as mock_validate:
            from lexibrary.validator.report import ValidationReport

            mock_validate.return_value = ValidationReport(issues=[])
            report = _run_coordinator(project, dry_run=True)

        # Should have dispatched count (dry-run records it)
        assert report.checked >= 1
        # But the file should not have been modified
        assert design.read_text(encoding="utf-8") == original_content

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_validation_results_feed_into_triage(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Validation issues are triaged alongside staleness issues."""
        project = _setup_minimal_project(tmp_path)

        with patch("lexibrary.validator.validate_library") as mock_validate:
            from lexibrary.validator.report import (
                ValidationIssue,
                ValidationReport,
            )

            mock_validate.return_value = ValidationReport(
                issues=[
                    ValidationIssue(
                        severity="warning",
                        check="stale_agent_design",
                        message="Agent-edited stale",
                        artifact="designs/src/foo.py.md",
                    ),
                ]
            )

            config = LexibraryConfig()
            coord = Coordinator(project, config)
            result = coord._collect()

        validation_items = [i for i in result.items if i.source == "validation"]
        assert len(validation_items) >= 1
        assert validation_items[0].check == "stale_agent_design"

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_validate_library_raises_continues(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """If validate_library() raises, collection continues with other sources."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "# content\n")
        _make_design_file(
            project,
            "src/foo.py",
            source_hash="old_hash",
            updated_by="archivist",
        )

        with patch(
            "lexibrary.validator.validate_library",
            side_effect=RuntimeError("validator crashed"),
        ):
            config = LexibraryConfig()
            coord = Coordinator(project, config)
            result = coord._collect()

        # Validation error recorded
        assert result.validation_error is not None
        assert "validator crashed" in result.validation_error
        # But staleness detection still ran
        staleness_items = [
            i for i in result.items if i.source == "staleness" and i.check == "staleness"
        ]
        assert len(staleness_items) >= 1
