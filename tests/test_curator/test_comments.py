"""Tests for the curator comment integration sub-agent.

Covers: comment detection (count > 0 flagged, count == 0 not flagged,
ranking by count), classification (durable, ephemeral, actionable),
Stack post deduplication, Insights section handling, write contract,
archivist preservation, integration flow, and idempotency.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.comments import (
    CommentClassification,
    CommentIntegrationResult,
    CommentWorkItem,
    _comment_integration_stub,
    _normalise_title,
    _update_comments_sidecar,
    comment_result_to_sub_agent_result,
    compute_stack_fingerprint,
    find_matching_open_post,
    integrate_comments,
    promote_to_stack_post,
)
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.models import (
    CommentCollectItem,
    CuratorReport,
)
from lexibrary.lifecycle.models import ArtefactComment

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
    preserved_sections: dict[str, str] | None = None,
) -> Path:
    """Create a minimal design file matching a source path."""
    design_path = project_root / ".lexibrary" / "designs" / f"{source_rel}.md"
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


def _make_comments_yaml(
    design_path: Path,
    comments: list[dict[str, str]],
) -> Path:
    """Create a .comments.yaml sidecar beside a design file."""
    comments_path = design_path.with_suffix(".comments.yaml")
    data = {
        "comments": [
            {"body": c["body"], "date": c.get("date", "2026-04-01T12:00:00")} for c in comments
        ]
    }
    comments_path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return comments_path


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
# Comment detection tests
# ---------------------------------------------------------------------------


class TestCommentDetection:
    """Comment detection in the collect phase."""

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_file_with_comments_flagged(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        """Design file with .comments.yaml containing comments is flagged."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design_path = _make_design_file(project, "src/foo.py")
        _make_comments_yaml(
            design_path,
            [
                {"body": "Design rationale: chose dict registry for O(1) lookup"},
                {"body": "Updated tests for new API"},
                {"body": "Bug: silently swallows TimeoutError"},
            ],
        )

        config = LexibraryConfig()
        coord = Coordinator(project, config)
        result = coord._collect()

        assert len(result.comment_items) == 1
        assert result.comment_items[0].comment_count == 3

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_file_with_no_comments_not_flagged(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        """Design file with no .comments.yaml is not flagged."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/bar.py", "def bar(): pass\n")
        _make_design_file(project, "src/bar.py")

        config = LexibraryConfig()
        coord = Coordinator(project, config)
        result = coord._collect()

        assert len(result.comment_items) == 0

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_file_with_empty_comments_not_flagged(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        """Design file with empty .comments.yaml is not flagged."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/baz.py", "def baz(): pass\n")
        design_path = _make_design_file(project, "src/baz.py")
        # Create an empty comments file
        comments_path = design_path.with_suffix(".comments.yaml")
        comments_path.write_text("comments: []\n", encoding="utf-8")

        config = LexibraryConfig()
        coord = Coordinator(project, config)
        result = coord._collect()

        assert len(result.comment_items) == 0

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    def test_ranking_by_comment_count(
        self, _mock_iwh: MagicMock, _mock_uncommitted: MagicMock, tmp_path: Path
    ) -> None:
        """Files with more comments are ranked higher."""
        project = _setup_minimal_project(tmp_path)

        # File with 1 comment
        _make_source_file(project, "src/low.py", "def low(): pass\n")
        dp_low = _make_design_file(project, "src/low.py")
        _make_comments_yaml(dp_low, [{"body": "one comment"}])

        # File with 5 comments
        _make_source_file(project, "src/high.py", "def high(): pass\n")
        dp_high = _make_design_file(project, "src/high.py")
        _make_comments_yaml(
            dp_high,
            [{"body": f"comment {i}"} for i in range(5)],
        )

        config = LexibraryConfig()
        coord = Coordinator(project, config)
        result = coord._collect()

        assert len(result.comment_items) == 2
        # Higher count first
        assert result.comment_items[0].comment_count == 5
        assert result.comment_items[1].comment_count == 1


# ---------------------------------------------------------------------------
# Comment classification tests (stub)
# ---------------------------------------------------------------------------


class TestCommentClassification:
    """Classification via the BAML stub."""

    def test_durable_design_rationale(self) -> None:
        """A design rationale comment is classified as durable."""
        comments = [
            ArtefactComment(
                body="We chose dict-based registry because it gives O(1) lookup",
                date=datetime.now(UTC),
            )
        ]
        result = _comment_integration_stub(
            design_content="# Test",
            comments=comments,
            source_content=None,
        )
        assert result.success
        assert len(result.classifications) == 1
        assert result.classifications[0].disposition == "durable"

    def test_ephemeral_progress_note(self) -> None:
        """A progress note is classified as ephemeral."""
        comments = [
            ArtefactComment(
                body="Updated the tests for new validation logic",
                date=datetime.now(UTC),
            )
        ]
        result = _comment_integration_stub(
            design_content="# Test",
            comments=comments,
            source_content=None,
        )
        assert result.success
        assert len(result.classifications) == 1
        assert result.classifications[0].disposition == "ephemeral"

    def test_actionable_bug_report(self) -> None:
        """A bug report comment is classified as actionable."""
        comments = [
            ArtefactComment(
                body="Bug: process_batch silently swallows TimeoutError",
                date=datetime.now(UTC),
            )
        ]
        result = _comment_integration_stub(
            design_content="# Test",
            comments=comments,
            source_content=None,
        )
        assert result.success
        assert len(result.classifications) == 1
        assert result.classifications[0].disposition == "actionable"
        assert result.classifications[0].promotion_title
        assert result.classifications[0].promotion_problem

    def test_mixed_classifications(self) -> None:
        """Multiple comments get different classifications."""
        comments = [
            ArtefactComment(
                body="We chose this approach for thread safety",
                date=datetime.now(UTC),
            ),
            ArtefactComment(
                body="Updated the imports to use new module",
                date=datetime.now(UTC),
            ),
            ArtefactComment(
                body="Error: missing null check causes crash",
                date=datetime.now(UTC),
            ),
        ]
        result = _comment_integration_stub(
            design_content="# Test",
            comments=comments,
            source_content=None,
        )
        assert result.success
        assert len(result.classifications) == 3
        dispositions = [c.disposition for c in result.classifications]
        assert "durable" in dispositions
        assert "ephemeral" in dispositions
        assert "actionable" in dispositions


# ---------------------------------------------------------------------------
# Stack post deduplication tests
# ---------------------------------------------------------------------------


class TestStackPostDedup:
    """Stack post deduplication via fingerprinting."""

    def test_fingerprint_deterministic(self) -> None:
        """Same inputs produce the same fingerprint."""
        fp1 = compute_stack_fingerprint("src/foo.py", "bug", "Timeout error in batch")
        fp2 = compute_stack_fingerprint("src/foo.py", "bug", "Timeout error in batch")
        assert fp1 == fp2

    def test_fingerprint_normalises_title(self) -> None:
        """Punctuation and case differences produce the same fingerprint."""
        fp1 = compute_stack_fingerprint("src/foo.py", "bug", "Timeout Error!")
        fp2 = compute_stack_fingerprint("src/foo.py", "bug", "timeout  error")
        assert fp1 == fp2

    def test_fingerprint_differs_on_source(self) -> None:
        """Different source paths produce different fingerprints."""
        fp1 = compute_stack_fingerprint("src/foo.py", "bug", "error")
        fp2 = compute_stack_fingerprint("src/bar.py", "bug", "error")
        assert fp1 != fp2

    def test_matching_post_gets_finding_appended(self, tmp_path: Path) -> None:
        """When a matching post exists, a Finding is appended."""
        stack_dir = tmp_path / "stack"
        stack_dir.mkdir()

        # Create a post first
        post_path, is_new = promote_to_stack_post(
            stack_dir,
            source_path="src/foo.py",
            title="Timeout Error",
            problem="process_batch silently swallows TimeoutError",
            category="bug",
        )
        assert is_new

        # Promote again with same fingerprint -- should append
        post_path2, is_new2 = promote_to_stack_post(
            stack_dir,
            source_path="src/foo.py",
            title="Timeout Error",
            problem="Also happens in process_single",
            category="bug",
        )
        assert not is_new2
        assert post_path2 == post_path

    def test_no_matching_post_creates_new(self, tmp_path: Path) -> None:
        """When no matching post exists, a new post is created."""
        stack_dir = tmp_path / "stack"
        stack_dir.mkdir()

        post_path, is_new = promote_to_stack_post(
            stack_dir,
            source_path="src/foo.py",
            title="Timeout Error",
            problem="process_batch silently swallows TimeoutError",
            category="bug",
        )
        assert is_new
        assert post_path.exists()

    def test_find_matching_open_post_returns_none_for_empty_dir(self, tmp_path: Path) -> None:
        """Returns None if stack directory is empty."""
        stack_dir = tmp_path / "stack"
        stack_dir.mkdir()
        result = find_matching_open_post(stack_dir, "somefingerprint")
        assert result is None


# ---------------------------------------------------------------------------
# Insights section tests
# ---------------------------------------------------------------------------


class TestInsightsSection:
    """Insights section creation and appending."""

    def test_insights_created_when_absent(self, tmp_path: Path) -> None:
        """Insights section is created when design file has none."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design_path = _make_design_file(project, "src/foo.py")

        comments = [
            ArtefactComment(
                body="Thread safety requires external lock",
                date=datetime.now(UTC),
            )
        ]
        comments_path = _make_comments_yaml(design_path, [{"body": c.body} for c in comments])

        work_item = CommentWorkItem(
            design_path=design_path,
            source_path=project / "src" / "foo.py",
            comments_path=comments_path,
            comments=comments,
        )

        result = integrate_comments(work_item, project)
        assert result.success

        # Re-parse design file and check Insights
        df = parse_design_file(design_path)
        assert df is not None
        assert "Insights" in df.preserved_sections
        assert "Thread safety" in df.preserved_sections["Insights"]

    def test_insights_appended_when_exists(self, tmp_path: Path) -> None:
        """New insights are appended to existing Insights section."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design_path = _make_design_file(
            project,
            "src/foo.py",
            preserved_sections={"Insights": "- Existing insight about concurrency"},
        )

        comments = [
            ArtefactComment(
                body="Registry uses lazy initialization for performance",
                date=datetime.now(UTC),
            )
        ]
        comments_path = _make_comments_yaml(design_path, [{"body": c.body} for c in comments])

        work_item = CommentWorkItem(
            design_path=design_path,
            source_path=project / "src" / "foo.py",
            comments_path=comments_path,
            comments=comments,
        )

        result = integrate_comments(work_item, project)
        assert result.success

        df = parse_design_file(design_path)
        assert df is not None
        insights = df.preserved_sections.get("Insights", "")
        assert "Existing insight" in insights
        assert "lazy initialization" in insights

    def test_insights_placed_after_deps(self, tmp_path: Path) -> None:
        """Insights section appears after Dependencies/Dependents in serialized output."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design_path = _make_design_file(project, "src/foo.py")

        comments = [
            ArtefactComment(
                body="Callers must hold the registry lock",
                date=datetime.now(UTC),
            )
        ]
        comments_path = _make_comments_yaml(design_path, [{"body": c.body} for c in comments])

        work_item = CommentWorkItem(
            design_path=design_path,
            source_path=project / "src" / "foo.py",
            comments_path=comments_path,
            comments=comments,
        )

        result = integrate_comments(work_item, project)
        assert result.success

        content = design_path.read_text(encoding="utf-8")
        deps_pos = content.find("## Dependents")
        insights_pos = content.find("## Insights")
        footer_pos = content.find("<!-- lexibrary:meta")
        assert deps_pos < insights_pos < footer_pos


# ---------------------------------------------------------------------------
# Write contract tests
# ---------------------------------------------------------------------------


class TestWriteContract:
    """Write contract enforcement for comment integration."""

    def test_updated_by_curator(self, tmp_path: Path) -> None:
        """Design file is written with updated_by: curator."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design_path = _make_design_file(project, "src/foo.py")

        comments = [
            ArtefactComment(
                body="Important design rationale",
                date=datetime.now(UTC),
            )
        ]
        comments_path = _make_comments_yaml(design_path, [{"body": c.body} for c in comments])

        work_item = CommentWorkItem(
            design_path=design_path,
            source_path=project / "src" / "foo.py",
            comments_path=comments_path,
            comments=comments,
        )

        result = integrate_comments(work_item, project)
        assert result.success

        df = parse_design_file(design_path)
        assert df is not None
        assert df.frontmatter.updated_by == "curator"

    def test_hashes_fresh(self, tmp_path: Path) -> None:
        """Design file is written with fresh hashes matching current source."""
        project = _setup_minimal_project(tmp_path)
        source_path = _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design_path = _make_design_file(project, "src/foo.py", source_hash="old_hash")

        from lexibrary.ast_parser import compute_hashes

        expected_source_hash, expected_interface_hash = compute_hashes(source_path)

        comments = [
            ArtefactComment(
                body="This is a design note",
                date=datetime.now(UTC),
            )
        ]
        comments_path = _make_comments_yaml(design_path, [{"body": c.body} for c in comments])

        work_item = CommentWorkItem(
            design_path=design_path,
            source_path=source_path,
            comments_path=comments_path,
            comments=comments,
        )

        result = integrate_comments(work_item, project)
        assert result.success

        df = parse_design_file(design_path)
        assert df is not None
        assert df.metadata.source_hash == expected_source_hash

    def test_consumed_comments_marked(self, tmp_path: Path) -> None:
        """Consumed comments (durable + actionable) are removed from sidecar."""
        project = _setup_minimal_project(tmp_path)
        _make_source_file(project, "src/foo.py", "def foo(): pass\n")
        design_path = _make_design_file(project, "src/foo.py")

        comments = [
            ArtefactComment(
                body="Design rationale: important",
                date=datetime.now(UTC),
            ),
            ArtefactComment(
                body="Updated the tests",
                date=datetime.now(UTC),
            ),
            ArtefactComment(
                body="Bug: crash on empty input",
                date=datetime.now(UTC),
            ),
        ]
        comments_path = _make_comments_yaml(
            design_path,
            [{"body": c.body} for c in comments],
        )

        work_item = CommentWorkItem(
            design_path=design_path,
            source_path=project / "src" / "foo.py",
            comments_path=comments_path,
            comments=comments,
        )

        result = integrate_comments(work_item, project)
        assert result.success

        # Check dispositions
        dispositions = {c.disposition for c in result.classifications}
        assert "durable" in dispositions
        assert "ephemeral" in dispositions
        assert "actionable" in dispositions

        # Ephemeral comment should remain in sidecar
        if comments_path.exists():
            data = yaml.safe_load(comments_path.read_text(encoding="utf-8"))
            remaining_bodies = [c["body"] for c in data.get("comments", [])]
            # Only ephemeral should remain
            assert "Updated the tests" in remaining_bodies
            # Durable and actionable should be consumed
            assert "Design rationale: important" not in remaining_bodies
            assert "Bug: crash on empty input" not in remaining_bodies
        else:
            # If no ephemeral, file might be deleted
            pass


# ---------------------------------------------------------------------------
# Triage classification tests
# ---------------------------------------------------------------------------


class TestTriageCommentClassification:
    """Comment items are triaged with correct issue_type and action_key."""

    def test_comment_classified_as_comment_type(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        comment_item = CommentCollectItem(
            design_path=Path("/fake/design.md"),
            source_path=Path("src/foo.py"),
            comment_count=3,
            comments_path=Path("/fake/design.comments.yaml"),
        )

        triage_item = coord._classify_comment(comment_item)
        assert triage_item.issue_type == "comment"
        assert triage_item.action_key == "integrate_sidecar_comments"
        assert triage_item.comment_item is comment_item

    def test_comment_priority_scales_with_count(self, tmp_path: Path) -> None:
        project = _setup_minimal_project(tmp_path)
        config = LexibraryConfig()
        coord = Coordinator(project, config)

        item_low = coord._classify_comment(
            CommentCollectItem(
                design_path=Path("/fake/low.md"),
                source_path=Path("src/low.py"),
                comment_count=1,
                comments_path=Path("/fake/low.comments.yaml"),
            )
        )
        item_high = coord._classify_comment(
            CommentCollectItem(
                design_path=Path("/fake/high.md"),
                source_path=Path("src/high.py"),
                comment_count=10,
                comments_path=Path("/fake/high.comments.yaml"),
            )
        )

        assert item_high.priority > item_low.priority


# ---------------------------------------------------------------------------
# Integration end-to-end tests
# ---------------------------------------------------------------------------


class TestEndToEndCommentIntegration:
    """End-to-end comment integration through the coordinator."""

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_end_to_end_three_comments(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """3 comments: 1 durable (integrated), 1 ephemeral (pruned), 1 actionable (promoted)."""
        project = _setup_minimal_project(tmp_path)
        source_path = _make_source_file(project, "src/foo.py", "def foo(): pass\n")

        # Use matching hashes to avoid staleness detection interference
        from lexibrary.ast_parser import compute_hashes

        src_hash, ifc_hash = compute_hashes(source_path)
        design_path = _make_design_file(
            project, "src/foo.py", source_hash=src_hash, interface_hash=ifc_hash
        )
        _make_comments_yaml(
            design_path,
            [
                {"body": "We chose this pattern for backward compatibility"},
                {"body": "Updated tests to cover edge case"},
                {"body": "Bug: missing null check causes crash"},
            ],
        )

        with patch("lexibrary.validator.validate_library") as mock_validate:
            from lexibrary.validator.report import ValidationReport

            mock_validate.return_value = ValidationReport(issues=[])

            report = _run_coordinator(project)

        # Comment integration should have been dispatched
        assert "integrate_sidecar_comments" in report.sub_agent_calls

        # Design file should have Insights section
        df = parse_design_file(design_path)
        assert df is not None
        assert df.frontmatter.updated_by == "curator"
        assert "Insights" in df.preserved_sections
        assert "backward compatibility" in df.preserved_sections["Insights"]

    @patch("lexibrary.curator.coordinator._uncommitted_files", return_value=set())
    @patch("lexibrary.curator.coordinator._active_iwh_dirs", return_value=set())
    @patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None)
    def test_idempotency_second_run_no_changes(
        self,
        _mock_graph: MagicMock,
        _mock_iwh: MagicMock,
        _mock_uncommitted: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Second run with no new comments produces no changes."""
        project = _setup_minimal_project(tmp_path)
        source_path = _make_source_file(project, "src/foo.py", "def foo(): pass\n")

        from lexibrary.ast_parser import compute_hashes

        src_hash, ifc_hash = compute_hashes(source_path)
        design_path = _make_design_file(
            project, "src/foo.py", source_hash=src_hash, interface_hash=ifc_hash
        )
        _make_comments_yaml(
            design_path,
            [{"body": "Design choice: immutable for thread safety"}],
        )

        with patch("lexibrary.validator.validate_library") as mock_validate:
            from lexibrary.validator.report import ValidationReport

            mock_validate.return_value = ValidationReport(issues=[])

            # First run
            _run_coordinator(project)

            # Second run -- no new comments, should not re-process
            report2 = _run_coordinator(project)

        # No comment integration dispatched on second run
        assert report2.sub_agent_calls.get("integrate_sidecar_comments", 0) == 0


# ---------------------------------------------------------------------------
# Sidecar update tests
# ---------------------------------------------------------------------------


class TestSidecarUpdate:
    """Tests for _update_comments_sidecar."""

    def test_all_consumed_removes_file(self, tmp_path: Path) -> None:
        """When all comments are consumed (durable/actionable), the sidecar is deleted."""
        comments_path = tmp_path / "test.comments.yaml"
        comments_path.write_text(
            yaml.dump(
                {
                    "comments": [
                        {"body": "design note", "date": "2026-04-01T12:00:00"},
                    ]
                },
                default_flow_style=False,
            ),
            encoding="utf-8",
        )

        classifications = [
            CommentClassification(
                comment=ArtefactComment(
                    body="design note",
                    date=datetime(2026, 4, 1, 12, 0, 0),
                ),
                disposition="durable",
                insight_text="- design note",
            )
        ]

        _update_comments_sidecar(comments_path, classifications)
        assert not comments_path.exists()

    def test_ephemeral_remains(self, tmp_path: Path) -> None:
        """Ephemeral comments remain in the sidecar file."""
        comments_path = tmp_path / "test.comments.yaml"
        comments_path.write_text(
            yaml.dump(
                {
                    "comments": [
                        {"body": "design note", "date": "2026-04-01T12:00:00"},
                        {"body": "progress update", "date": "2026-04-01T12:00:00"},
                    ]
                },
                default_flow_style=False,
            ),
            encoding="utf-8",
        )

        classifications = [
            CommentClassification(
                comment=ArtefactComment(
                    body="design note",
                    date=datetime(2026, 4, 1, 12, 0, 0),
                ),
                disposition="durable",
            ),
            CommentClassification(
                comment=ArtefactComment(
                    body="progress update",
                    date=datetime(2026, 4, 1, 12, 0, 0),
                ),
                disposition="ephemeral",
            ),
        ]

        _update_comments_sidecar(comments_path, classifications)
        assert comments_path.exists()
        data = yaml.safe_load(comments_path.read_text(encoding="utf-8"))
        assert len(data["comments"]) == 1
        assert data["comments"][0]["body"] == "progress update"


# ---------------------------------------------------------------------------
# Title normalisation tests
# ---------------------------------------------------------------------------


class TestTitleNormalisation:
    """Tests for _normalise_title."""

    def test_lowercase_and_strip_punctuation(self) -> None:
        assert _normalise_title("Hello, World!") == "hello world"

    def test_collapse_whitespace(self) -> None:
        assert _normalise_title("  too   many   spaces  ") == "too many spaces"

    def test_empty_string(self) -> None:
        assert _normalise_title("") == ""


# ---------------------------------------------------------------------------
# Result conversion tests
# ---------------------------------------------------------------------------


class TestResultConversion:
    """Tests for comment_result_to_sub_agent_result."""

    def test_success_conversion(self) -> None:
        result = CommentIntegrationResult(
            success=True,
            message="done",
            llm_calls=1,
        )
        sub_result = comment_result_to_sub_agent_result(result, Path("src/foo.py"))
        assert sub_result.success
        assert sub_result.action_key == "integrate_sidecar_comments"
        assert sub_result.llm_calls == 1

    def test_failure_conversion(self) -> None:
        result = CommentIntegrationResult(
            success=False,
            message="parse error",
            llm_calls=0,
        )
        sub_result = comment_result_to_sub_agent_result(result)
        assert not sub_result.success
        assert sub_result.path is None
