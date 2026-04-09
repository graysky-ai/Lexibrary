"""Integration tests for curator Phase 3 end-to-end pipeline.

Tests the full collect-triage-dispatch-report pipeline using the
``curator_library`` fixture and controlled mocks for BAML LLM calls.

Covers:
(a) Post-edit reactive run: editing a source file triggers a scoped curator
    check that detects the corresponding design file is stale.
(b) Budget Trimmer under ``auto_low``: the over-budget file is NOT modified;
    a proposal appears in the report.
(c) Budget Trimmer under ``full``: the file is condensed and rewritten.
(d) Comment auditing under ``auto_low``: stale TODO is proposed for removal,
    not auto-removed.
(e) Scoped run produces a report with ``trigger="reactive_post_edit"``.
"""

from __future__ import annotations

import shutil
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
from lexibrary.ast_parser import compute_hashes
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.models import CuratorReport

# ---------------------------------------------------------------------------
# Fixture directory
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "curator_library"


@pytest.fixture()
def integration_project(tmp_path: Path) -> Path:
    """Return an isolated copy of the curator_library fixture for integration tests.

    Creates a fresh copy so tests can modify files freely.
    """
    dest = tmp_path / "curator_library"
    shutil.copytree(_FIXTURE_DIR, dest)
    # Ensure curator directory exists for locks/reports
    (dest / ".lexibrary" / "curator").mkdir(parents=True, exist_ok=True)
    return dest


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
    body_content: str = "",
) -> Path:
    """Create a minimal design file matching a source path."""
    design_path = project_root / ".lexibrary" / "designs" / (source_rel + ".md")
    design_path.parent.mkdir(parents=True, exist_ok=True)

    preserved = {}
    if body_content:
        preserved["Insights"] = body_content

    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Test design file",
            id=source_rel.replace("/", "-").replace(".", "-"),
            updated_by=updated_by,
            status="active",
        ),
        summary="Test summary",
        interface_contract="def test_func(): ...",
        dependencies=[],
        dependents=[],
        preserved_sections=preserved,
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


def _make_oversized_design_file(
    project_root: Path,
    source_rel: str,
    *,
    match_hashes: bool = True,
) -> Path:
    """Create a design file that exceeds the default 4000-token budget.

    When match_hashes is True, computes the real source/interface hashes
    from the source file so that the staleness detector does NOT trigger
    a hash mismatch alongside the budget issue.
    """
    large_content = "This is filler content for budget testing. " * 600

    source_hash = "abc123"
    interface_hash: str | None = None
    if match_hashes:
        source_path = project_root / source_rel
        if source_path.exists():
            source_hash, interface_hash = compute_hashes(source_path)

    return _make_design_file(
        project_root,
        source_rel,
        source_hash=source_hash,
        interface_hash=interface_hash,
        body_content=large_content,
    )


def _read_file_content(path: Path) -> str:
    """Read and return file content as a string."""
    return path.read_text(encoding="utf-8")


def _mock_condense_result() -> MagicMock:
    """Create a mock BAML condense result."""
    result = MagicMock()
    result.condensed_content = "---\ndescription: Condensed\n---\n# Condensed\n\nShort content.\n"
    result.trimmed_sections = ["Design Rationale", "Historical Context"]
    return result


def _mock_audit_comment_result(staleness: str = "STALE") -> MagicMock:
    """Create a mock BAML audit comment result."""
    result = MagicMock()
    result.staleness = MagicMock()
    result.staleness.value = staleness
    result.reasoning = f"Comment assessed as {staleness.lower()}"
    return result


# ---------------------------------------------------------------------------
# (a) Post-edit reactive run: stale design detection
# ---------------------------------------------------------------------------


class TestPostEditReactiveRun:
    """Editing a source file triggers a scoped curator check that detects
    the corresponding design file is stale."""

    @pytest.mark.asyncio
    async def test_edit_triggers_staleness_detection(self, integration_project: Path) -> None:
        """Modifying a source file makes its design file appear stale.

        When the coordinator runs with scope set to the modified source
        file, the collect phase detects hash mismatch between the current
        source and the recorded source_hash in the design file metadata.
        """
        project = integration_project

        # The fixture has src/utils/helpers.py with a matching design file.
        # Modify the source to create a hash mismatch.
        source_path = project / "src" / "utils" / "helpers.py"
        original = source_path.read_text(encoding="utf-8")
        source_path.write_text(
            original + "\ndef new_function():\n    return 'added'\n",
            encoding="utf-8",
        )

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        # Run with scope limited to the modified file
        result = coord._collect(scope=source_path)

        # The staleness check should detect a hash mismatch
        stale_items = [
            item
            for item in result.items
            if item.source == "staleness" and item.check == "staleness"
        ]
        assert len(stale_items) >= 1
        assert any(item.path == source_path for item in stale_items)

    @pytest.mark.asyncio
    async def test_scoped_run_produces_report_with_trigger(self, integration_project: Path) -> None:
        """A scoped run with reactive_post_edit trigger records it in the report."""
        project = integration_project

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        report = await coord.run(
            scope=project / "src" / "utils",
            trigger="reactive_post_edit",
        )

        assert isinstance(report, CuratorReport)
        assert report.trigger == "reactive_post_edit"


# ---------------------------------------------------------------------------
# (b) Budget Trimmer under auto_low: proposals only
# ---------------------------------------------------------------------------


class TestBudgetTrimmerAutoLow:
    """Under auto_low autonomy, over-budget files are NOT modified;
    a proposal appears in the report."""

    @pytest.mark.asyncio
    async def test_over_budget_file_not_modified(self, tmp_path: Path) -> None:
        """Under auto_low, condense_file (High risk) is deferred.

        The over-budget file remains unchanged on disk, and the report
        contains zero budget_condensed and a deferred entry.
        """
        project = tmp_path / "proj"
        project.mkdir()
        lex = project / ".lexibrary"
        lex.mkdir()
        (lex / "designs").mkdir()
        (lex / "curator").mkdir()

        # Create source + oversized design
        _make_source_file(project, "src/big_module.py", "def big(): pass\n")
        design_path = _make_oversized_design_file(project, "src/big_module.py")
        original_content = _read_file_content(design_path)

        # auto_low is the default autonomy
        config = LexibraryConfig()
        assert config.curator.autonomy == "auto_low"

        coord = Coordinator(project, config)
        report = await coord.run()

        # File should NOT be modified
        assert _read_file_content(design_path) == original_content
        # No condensations should have been executed
        assert report.budget_condensed == 0
        # The high-risk condense_file action should be deferred
        assert report.deferred >= 1

    @pytest.mark.asyncio
    async def test_proposal_appears_in_deferred(self, tmp_path: Path) -> None:
        """Under auto_low, budget issues appear in the report's deferred count."""
        project = tmp_path / "proj"
        project.mkdir()
        lex = project / ".lexibrary"
        lex.mkdir()
        (lex / "designs").mkdir()
        (lex / "curator").mkdir()

        _make_source_file(project, "src/large.py", "def large(): pass\n")
        _make_oversized_design_file(project, "src/large.py")

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        # Collect + triage to inspect items
        collect = coord._collect()
        triage = coord._triage(collect)

        # Budget items should appear in triage with high risk
        budget_items = [t for t in triage.items if t.issue_type == "budget"]
        assert len(budget_items) >= 1
        assert budget_items[0].risk_level == "high"
        assert budget_items[0].action_key == "condense_file"


# ---------------------------------------------------------------------------
# (c) Budget Trimmer under full: condensation and rewrite
# ---------------------------------------------------------------------------


class TestBudgetTrimmerFull:
    """Under full autonomy, the over-budget file is condensed and rewritten."""

    @pytest.mark.asyncio
    async def test_condensed_file_is_rewritten(self, tmp_path: Path) -> None:
        """Under full autonomy, condense_file rewrites the design file.

        Mocks the BAML CuratorCondenseFile call and verifies the file is
        written with the condensed content.
        """
        project = tmp_path / "proj"
        project.mkdir()
        lex = project / ".lexibrary"
        lex.mkdir()
        (lex / "designs").mkdir()
        (lex / "curator").mkdir()

        _make_source_file(project, "src/fat.py", "def fat(): pass\n")
        design_path = _make_oversized_design_file(project, "src/fat.py")
        original_content = _read_file_content(design_path)

        config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
        coord = Coordinator(project, config)

        # Mock the BAML condense call
        mock_baml = AsyncMock()
        mock_baml.CuratorCondenseFile.return_value = _mock_condense_result()

        with patch("lexibrary.curator.budget.b", mock_baml):
            report = await coord.run()

        # The file should have been rewritten with condensed content
        new_content = _read_file_content(design_path)
        assert new_content != original_content
        assert report.budget_condensed >= 1

    @pytest.mark.asyncio
    async def test_report_reflects_condensation(self, tmp_path: Path) -> None:
        """Report budget_condensed count increments on successful condensation."""
        project = tmp_path / "proj"
        project.mkdir()
        lex = project / ".lexibrary"
        lex.mkdir()
        (lex / "designs").mkdir()
        (lex / "curator").mkdir()

        _make_source_file(project, "src/verbose.py", "def verbose(): pass\n")
        _make_oversized_design_file(project, "src/verbose.py")

        config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
        coord = Coordinator(project, config)

        mock_baml = AsyncMock()
        mock_baml.CuratorCondenseFile.return_value = _mock_condense_result()

        with patch("lexibrary.curator.budget.b", mock_baml):
            report = await coord.run()

        assert report.budget_condensed >= 1
        assert "condense_file" in report.sub_agent_calls


# ---------------------------------------------------------------------------
# (d) Comment auditing under auto_low: proposed, not auto-removed
# ---------------------------------------------------------------------------


class TestCommentAuditingAutoLow:
    """Under auto_low, stale TODO is proposed for removal, not auto-removed."""

    @pytest.mark.asyncio
    async def test_stale_todo_not_removed_auto_low(self, tmp_path: Path) -> None:
        """Under auto_low, flag_stale_comment (Medium risk) is deferred.

        The source file should remain unchanged because auto_low only
        dispatches low-risk actions, and flag_stale_comment is medium risk.
        The comment audit item appears as deferred in the report.
        """
        project = tmp_path / "proj"
        project.mkdir()
        lex = project / ".lexibrary"
        lex.mkdir()
        (lex / "designs").mkdir()
        (lex / "curator").mkdir()

        source_content = (
            '"""Module with stale TODO."""\n'
            "from __future__ import annotations\n\n"
            "def validated_func(data):\n"
            "    # TODO: add validation\n"
            "    if not isinstance(data, dict):\n"
            "        raise TypeError('Expected dict')\n"
            "    return data\n"
        )
        source_path = _make_source_file(project, "src/stale_mod.py", source_content)
        original_content = _read_file_content(source_path)

        config = LexibraryConfig()
        assert config.curator.autonomy == "auto_low"

        coord = Coordinator(project, config)
        report = await coord.run()

        # Source file should NOT be modified
        assert _read_file_content(source_path) == original_content
        # Under auto_low, medium-risk flag_stale_comment is deferred
        assert report.comments_flagged == 0
        # The deferred count should include the comment audit item
        assert report.deferred >= 1

    @pytest.mark.asyncio
    async def test_stale_todo_flagged_under_full(self, tmp_path: Path) -> None:
        """Under full autonomy, flag_stale_comment is dispatched and flagged."""
        project = tmp_path / "proj"
        project.mkdir()
        lex = project / ".lexibrary"
        lex.mkdir()
        (lex / "designs").mkdir()
        (lex / "curator").mkdir()

        source_content = (
            '"""Module with stale TODO."""\n'
            "from __future__ import annotations\n\n"
            "def validated_func(data):\n"
            "    # TODO: add validation\n"
            "    if not isinstance(data, dict):\n"
            "        raise TypeError('Expected dict')\n"
            "    return data\n"
        )
        source_path = _make_source_file(project, "src/stale_mod.py", source_content)
        original_content = _read_file_content(source_path)

        config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
        coord = Coordinator(project, config)

        # Mock the BAML audit call
        mock_baml = AsyncMock()
        mock_baml.CuratorAuditComment.return_value = _mock_audit_comment_result("STALE")

        with patch("lexibrary.curator.auditing.b", mock_baml):
            report = await coord.run()

        # Source file should NOT be modified (auditing is read-only, only flags)
        assert _read_file_content(source_path) == original_content
        # Comments should be flagged in the report under full autonomy
        assert report.comments_flagged >= 1

    @pytest.mark.asyncio
    async def test_comment_audit_collected_and_triaged(self, tmp_path: Path) -> None:
        """Comment audit items are collected, triaged with correct risk level."""
        project = tmp_path / "proj"
        project.mkdir()
        lex = project / ".lexibrary"
        lex.mkdir()
        (lex / "designs").mkdir()
        (lex / "curator").mkdir()

        source_content = (
            '"""Module with markers."""\n'
            "from __future__ import annotations\n\n"
            "def func():\n"
            "    # FIXME: broken edge case\n"
            "    return None\n"
        )
        _make_source_file(project, "src/fixme_mod.py", source_content)

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        collect = coord._collect()
        assert len(collect.comment_audit_items) >= 1

        triage = coord._triage(collect)
        audit_items = [t for t in triage.items if t.issue_type == "comment_audit"]
        assert len(audit_items) >= 1
        assert audit_items[0].action_key == "flag_stale_comment"
        assert audit_items[0].risk_level == "medium"


# ---------------------------------------------------------------------------
# (e) Scoped run produces report with trigger field
# ---------------------------------------------------------------------------


class TestScopedRunTrigger:
    """Scoped coordinator runs correctly propagate the trigger value."""

    @pytest.mark.asyncio
    async def test_reactive_post_edit_trigger(self, tmp_path: Path) -> None:
        """A scoped run with trigger='reactive_post_edit' records it in the report."""
        project = tmp_path / "proj"
        project.mkdir()
        lex = project / ".lexibrary"
        lex.mkdir()
        (lex / "designs").mkdir()
        (lex / "curator").mkdir()

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        report = await coord.run(
            scope=project / "src",
            trigger="reactive_post_edit",
        )

        assert report.trigger == "reactive_post_edit"
        assert isinstance(report.report_path, Path)

    @pytest.mark.asyncio
    async def test_reactive_post_bead_close_trigger(self, tmp_path: Path) -> None:
        """A scoped run with trigger='reactive_post_bead_close' records it."""
        project = tmp_path / "proj"
        project.mkdir()
        lex = project / ".lexibrary"
        lex.mkdir()
        (lex / "designs").mkdir()
        (lex / "curator").mkdir()

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        report = await coord.run(
            scope=project / "src",
            trigger="reactive_post_bead_close",
        )

        assert report.trigger == "reactive_post_bead_close"

    @pytest.mark.asyncio
    async def test_trigger_persisted_in_json_report(self, tmp_path: Path) -> None:
        """The trigger field is written to the JSON report on disk."""
        import json

        project = tmp_path / "proj"
        project.mkdir()
        lex = project / ".lexibrary"
        lex.mkdir()
        (lex / "designs").mkdir()
        (lex / "curator").mkdir()

        config = LexibraryConfig()
        coord = Coordinator(project, config)

        report = await coord.run(trigger="reactive_post_edit")

        assert report.report_path is not None
        assert report.report_path.exists()
        data = json.loads(report.report_path.read_text(encoding="utf-8"))
        assert data["trigger"] == "reactive_post_edit"
