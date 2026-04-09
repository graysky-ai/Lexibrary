"""Tests for the curator comment auditing sub-agent.

Covers:
- scan_todo_comments: finds TODO, FIXME, HACK markers with correct context
- scan_todo_comments: extracts plus/minus 20 lines of context
- scan_todo_comments: returns empty list for clean files
- audit_comment: mocked BAML returns stale/current/uncertain assessments
- audit_description: mocked BAML returns quality score and correction
- audit_summary: mocked BAML returns quality score and rewrite
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, MagicMock

from lexibrary.curator.auditing import (
    CommentAuditIssue,
    CommentAuditResult,
    DescriptionAuditResult,
    SummaryAuditResult,
    audit_comment,
    audit_description,
    audit_summary,
    comment_audit_to_sub_agent_result,
    description_audit_to_sub_agent_result,
    scan_todo_comments,
    summary_audit_to_sub_agent_result,
)
from lexibrary.curator.config import CuratorConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_file(tmp_path: Path, name: str, content: str) -> Path:
    """Create a source file in tmp_path and return its path."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _make_baml_staleness_mock(
    staleness: Literal["STALE", "CURRENT", "UNCERTAIN"],
    reasoning: str,
) -> MagicMock:
    """Create a mock BAML CommentAuditOutput."""
    output = MagicMock()
    output.staleness = MagicMock()
    output.staleness.value = staleness
    output.reasoning = reasoning
    return output


# ---------------------------------------------------------------------------
# scan_todo_comments tests
# ---------------------------------------------------------------------------


class TestScanTodoComments:
    """Tests for scan_todo_comments."""

    def test_finds_todo_marker(self, tmp_path: Path) -> None:
        """scan_todo_comments detects a simple TODO comment."""
        src = _make_source_file(
            tmp_path,
            "module.py",
            "def foo():\n    # TODO: implement this\n    pass\n",
        )
        issues = scan_todo_comments(src)
        assert len(issues) == 1
        assert issues[0].marker_type == "TODO"
        assert issues[0].line_number == 2
        assert "TODO: implement this" in issues[0].comment_text

    def test_finds_fixme_marker(self, tmp_path: Path) -> None:
        """scan_todo_comments detects a FIXME comment."""
        src = _make_source_file(
            tmp_path,
            "module.py",
            "x = 1\n# FIXME: broken logic\ny = 2\n",
        )
        issues = scan_todo_comments(src)
        assert len(issues) == 1
        assert issues[0].marker_type == "FIXME"
        assert issues[0].line_number == 2

    def test_finds_hack_marker(self, tmp_path: Path) -> None:
        """scan_todo_comments detects a HACK comment."""
        src = _make_source_file(
            tmp_path,
            "module.py",
            "# HACK: workaround for upstream bug\nimport os\n",
        )
        issues = scan_todo_comments(src)
        assert len(issues) == 1
        assert issues[0].marker_type == "HACK"
        assert issues[0].line_number == 1

    def test_finds_multiple_markers(self, tmp_path: Path) -> None:
        """scan_todo_comments finds all three marker types in one file."""
        content = (
            "# TODO: first thing\n"
            "x = 1\n"
            "# FIXME: second thing\n"
            "y = 2\n"
            "# HACK: third thing\n"
        )
        src = _make_source_file(tmp_path, "module.py", content)
        issues = scan_todo_comments(src)
        assert len(issues) == 3
        markers = {i.marker_type for i in issues}
        assert markers == {"TODO", "FIXME", "HACK"}

    def test_case_insensitive(self, tmp_path: Path) -> None:
        """scan_todo_comments matches markers case-insensitively."""
        content = "# todo: lowercase\n# Fixme: mixed case\n# hack: all lower\n"
        src = _make_source_file(tmp_path, "module.py", content)
        issues = scan_todo_comments(src)
        assert len(issues) == 3

    def test_parenthetical_username(self, tmp_path: Path) -> None:
        """scan_todo_comments matches TODO(username) style markers."""
        src = _make_source_file(
            tmp_path,
            "module.py",
            "# TODO(jsmith): fix this later\n",
        )
        issues = scan_todo_comments(src)
        assert len(issues) == 1
        assert issues[0].marker_type == "TODO"
        assert "TODO(jsmith)" in issues[0].comment_text

    def test_empty_file(self, tmp_path: Path) -> None:
        """scan_todo_comments returns empty list for empty file."""
        src = _make_source_file(tmp_path, "empty.py", "")
        issues = scan_todo_comments(src)
        assert issues == []

    def test_clean_file_no_markers(self, tmp_path: Path) -> None:
        """scan_todo_comments returns empty list for a file with no markers."""
        content = (
            "\"\"\"A clean module.\"\"\"\n"
            "\n"
            "from __future__ import annotations\n"
            "\n"
            "\n"
            "def add(a: int, b: int) -> int:\n"
            "    # This is a regular comment\n"
            "    return a + b\n"
        )
        src = _make_source_file(tmp_path, "clean.py", content)
        issues = scan_todo_comments(src)
        assert issues == []

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """scan_todo_comments returns empty list for nonexistent file."""
        issues = scan_todo_comments(tmp_path / "nonexistent.py")
        assert issues == []

    def test_context_extraction_within_bounds(self, tmp_path: Path) -> None:
        """scan_todo_comments extracts plus/minus 20 lines of context."""
        # Build a file with a TODO at line 25 (1-based), so context starts
        # at line 5 (index 4) and ends at line 45 (index 44).
        lines = [f"line_{i}" for i in range(50)]
        lines[24] = "# TODO: marker at line 25"
        src = _make_source_file(tmp_path, "big.py", "\n".join(lines))

        issues = scan_todo_comments(src)
        assert len(issues) == 1
        assert issues[0].line_number == 25

        context_lines = issues[0].code_context.splitlines()
        # Context should be lines 5-45 (inclusive), i.e. 41 lines
        assert len(context_lines) == 41
        assert "line_4" in context_lines[0]  # line index 4 = line 5
        assert "# TODO: marker at line 25" in issues[0].code_context
        assert "line_44" in context_lines[-1]  # line index 44 = line 45

    def test_context_at_file_start(self, tmp_path: Path) -> None:
        """Context extraction clamps at beginning of file."""
        content = "# TODO: first line marker\n" + "\n".join(
            f"line_{i}" for i in range(30)
        )
        src = _make_source_file(tmp_path, "start.py", content)

        issues = scan_todo_comments(src)
        assert len(issues) == 1
        assert issues[0].line_number == 1
        context_lines = issues[0].code_context.splitlines()
        # Should start at line 1 (no negative lines) and go to line 21
        assert context_lines[0] == "# TODO: first line marker"
        assert len(context_lines) == 21

    def test_context_at_file_end(self, tmp_path: Path) -> None:
        """Context extraction clamps at end of file."""
        lines = [f"line_{i}" for i in range(10)]
        lines.append("# TODO: last area marker")
        src = _make_source_file(tmp_path, "end.py", "\n".join(lines))

        issues = scan_todo_comments(src)
        assert len(issues) == 1
        assert issues[0].line_number == 11
        context_lines = issues[0].code_context.splitlines()
        # Should contain all 11 lines (clamped at start and end)
        assert len(context_lines) == 11

    def test_path_stored_correctly(self, tmp_path: Path) -> None:
        """Returned issues store the correct source path."""
        src = _make_source_file(tmp_path, "mod.py", "# TODO: test\n")
        issues = scan_todo_comments(src)
        assert issues[0].path == src


# ---------------------------------------------------------------------------
# audit_comment tests (mocked BAML)
# ---------------------------------------------------------------------------


class TestAuditComment:
    """Tests for audit_comment with mocked BAML client."""

    def test_stale_assessment(self, tmp_path: Path) -> None:
        """audit_comment returns stale when BAML says stale."""
        issue = CommentAuditIssue(
            path=tmp_path / "mod.py",
            line_number=10,
            comment_text="# TODO: add validation",
            code_context="def validate(x):\n    if not x:\n        raise ValueError\n",
            marker_type="TODO",
        )

        mock_client = AsyncMock()
        mock_client.CuratorAuditComment.return_value = _make_baml_staleness_mock(
            "STALE", "Validation already implemented via validate()"
        )

        result = asyncio.run(audit_comment(issue, baml_client=mock_client))

        assert result.staleness == "stale"
        assert "Validation already implemented" in result.reasoning
        mock_client.CuratorAuditComment.assert_called_once_with(
            comment_text=issue.comment_text,
            code_context=issue.code_context,
        )

    def test_current_assessment(self, tmp_path: Path) -> None:
        """audit_comment returns current when BAML says current."""
        issue = CommentAuditIssue(
            path=tmp_path / "mod.py",
            line_number=5,
            comment_text="# FIXME: handle edge case",
            code_context="def process(data):\n    return data\n",
            marker_type="FIXME",
        )

        mock_client = AsyncMock()
        mock_client.CuratorAuditComment.return_value = _make_baml_staleness_mock(
            "CURRENT", "No edge case handling found in process()"
        )

        result = asyncio.run(audit_comment(issue, baml_client=mock_client))

        assert result.staleness == "current"
        assert "No edge case handling" in result.reasoning

    def test_uncertain_assessment(self, tmp_path: Path) -> None:
        """audit_comment returns uncertain when BAML says uncertain."""
        issue = CommentAuditIssue(
            path=tmp_path / "mod.py",
            line_number=3,
            comment_text="# HACK: see issue #1234",
            code_context="import os\nos.environ['KEY'] = 'val'\n",
            marker_type="HACK",
        )

        mock_client = AsyncMock()
        mock_client.CuratorAuditComment.return_value = _make_baml_staleness_mock(
            "UNCERTAIN", "External reference #1234 requires human review"
        )

        result = asyncio.run(audit_comment(issue, baml_client=mock_client))

        assert result.staleness == "uncertain"
        assert "#1234" in result.reasoning


# ---------------------------------------------------------------------------
# audit_description tests (mocked BAML)
# ---------------------------------------------------------------------------


class TestAuditDescription:
    """Tests for audit_description with mocked BAML client."""

    def test_high_quality_no_correction(self) -> None:
        """audit_description returns high quality score and empty correction."""
        config = CuratorConfig()

        mock_output = MagicMock()
        mock_output.quality_score = 0.9
        mock_output.correction = ""

        mock_client = AsyncMock()
        mock_client.CuratorAuditDescription.return_value = mock_output

        result = asyncio.run(
            audit_description(
                "Good description",
                "def foo(): pass",
                config,
                baml_client=mock_client,
            )
        )

        assert result.quality_score == 0.9
        assert result.correction == ""

    def test_low_quality_with_correction(self) -> None:
        """audit_description returns low quality score with a correction."""
        config = CuratorConfig()

        mock_output = MagicMock()
        mock_output.quality_score = 0.4
        mock_output.correction = "Corrected description of the module"

        mock_client = AsyncMock()
        mock_client.CuratorAuditDescription.return_value = mock_output

        result = asyncio.run(
            audit_description(
                "Wrong description",
                "class Calculator:\n    def add(self, a, b): return a + b\n",
                config,
                baml_client=mock_client,
            )
        )

        assert result.quality_score == 0.4
        assert result.correction == "Corrected description of the module"
        mock_client.CuratorAuditDescription.assert_called_once()

    def test_threshold_boundary(self) -> None:
        """audit_description accepts score exactly at threshold."""
        config = CuratorConfig()

        mock_output = MagicMock()
        mock_output.quality_score = 0.7
        mock_output.correction = ""

        mock_client = AsyncMock()
        mock_client.CuratorAuditDescription.return_value = mock_output

        result = asyncio.run(
            audit_description(
                "Adequate description",
                "x = 1",
                config,
                baml_client=mock_client,
            )
        )

        assert result.quality_score == 0.7
        assert result.correction == ""


# ---------------------------------------------------------------------------
# audit_summary tests (mocked BAML)
# ---------------------------------------------------------------------------


class TestAuditSummary:
    """Tests for audit_summary with mocked BAML client."""

    def test_high_quality_no_rewrite(self) -> None:
        """audit_summary returns high quality score and empty rewrite."""
        config = CuratorConfig()

        mock_output = MagicMock()
        mock_output.quality_score = 0.85
        mock_output.rewrite = ""

        mock_client = AsyncMock()
        mock_client.CuratorAuditSummary.return_value = mock_output

        result = asyncio.run(
            audit_summary(
                "Good summary of the module",
                "def main(): pass",
                config,
                baml_client=mock_client,
            )
        )

        assert result.quality_score == 0.85
        assert result.rewrite == ""

    def test_low_quality_with_rewrite(self) -> None:
        """audit_summary returns low quality score with a rewrite."""
        config = CuratorConfig()

        mock_output = MagicMock()
        mock_output.quality_score = 0.3
        mock_output.rewrite = "Rewritten summary that accurately describes the module"

        mock_client = AsyncMock()
        mock_client.CuratorAuditSummary.return_value = mock_output

        result = asyncio.run(
            audit_summary(
                "Outdated summary",
                "class NewFeature:\n    def run(self): ...\n",
                config,
                baml_client=mock_client,
            )
        )

        assert result.quality_score == 0.3
        assert "Rewritten summary" in result.rewrite
        mock_client.CuratorAuditSummary.assert_called_once()


# ---------------------------------------------------------------------------
# Coordinator helper tests
# ---------------------------------------------------------------------------


class TestCoordinatorHelpers:
    """Tests for the SubAgentResult conversion helpers."""

    def test_comment_audit_to_sub_agent_result(self, tmp_path: Path) -> None:
        """comment_audit_to_sub_agent_result produces correct SubAgentResult."""
        issue = CommentAuditIssue(
            path=tmp_path / "mod.py",
            line_number=10,
            comment_text="# TODO: fix this",
            code_context="context",
            marker_type="TODO",
        )
        result = CommentAuditResult(staleness="stale", reasoning="Already done")
        sub = comment_audit_to_sub_agent_result(issue, result)

        assert sub.success is True
        assert sub.action_key == "flag_stale_comment"
        assert sub.path == tmp_path / "mod.py"
        assert "stale" in sub.message
        assert sub.llm_calls == 1

    def test_description_audit_to_sub_agent_result(self, tmp_path: Path) -> None:
        """description_audit_to_sub_agent_result produces correct SubAgentResult."""
        result = DescriptionAuditResult(quality_score=0.5, correction="Better desc")
        sub = description_audit_to_sub_agent_result(tmp_path / "mod.py", result)

        assert sub.success is True
        assert sub.action_key == "audit_description"
        assert "0.50" in sub.message
        assert "Better desc" in sub.message

    def test_description_audit_no_correction(self, tmp_path: Path) -> None:
        """description_audit_to_sub_agent_result with no correction."""
        result = DescriptionAuditResult(quality_score=0.9, correction="")
        sub = description_audit_to_sub_agent_result(tmp_path / "mod.py", result)

        assert "correction" not in sub.message

    def test_summary_audit_to_sub_agent_result(self, tmp_path: Path) -> None:
        """summary_audit_to_sub_agent_result produces correct SubAgentResult."""
        result = SummaryAuditResult(quality_score=0.4, rewrite="New summary")
        sub = summary_audit_to_sub_agent_result(tmp_path / "mod.py", result)

        assert sub.success is True
        assert sub.action_key == "audit_summary"
        assert "0.40" in sub.message
        assert "rewrite available" in sub.message

    def test_summary_audit_no_rewrite(self, tmp_path: Path) -> None:
        """summary_audit_to_sub_agent_result with no rewrite."""
        result = SummaryAuditResult(quality_score=0.8, rewrite="")
        sub = summary_audit_to_sub_agent_result(tmp_path / "mod.py", result)

        assert "rewrite" not in sub.message
