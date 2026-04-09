"""Tests for Phase 3: Budget Trimmer sub-agent.

Covers:
- scan_token_budgets detects over-budget design files
- scan_token_budgets skips files within budget
- scan_token_budgets detects over-budget START_HERE.md and HANDOFF.md
- condense_file with mocked BAML returns a CondenseResult
- condense_file does NOT write any files (coordinator responsibility)
- condense_file handles read errors gracefully
- condense_file handles BAML errors gracefully
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol
from unittest.mock import AsyncMock, MagicMock

from lexibrary.curator.budget import (
    BudgetIssue,
    condense_file,
    scan_token_budgets,
)
from lexibrary.curator.config import CuratorConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeTokenCounter(Protocol):
    """Protocol-matching fake for TokenCounter."""

    def count(self, text: str) -> int: ...
    def count_file(self, path: Path) -> int: ...
    @property
    def name(self) -> str: ...


class FixedTokenCounter:
    """Token counter that returns a fixed count per file, configurable via dict."""

    def __init__(self, file_counts: dict[str, int] | None = None, default: int = 100) -> None:
        self._file_counts = file_counts or {}
        self._default = default

    def count(self, text: str) -> int:
        return len(text) // 4

    def count_file(self, path: Path) -> int:
        return self._file_counts.get(str(path), self._default)

    @property
    def name(self) -> str:
        return "fixed-test"


def _make_design_file(project_root: Path, rel_path: str, content: str) -> Path:
    """Create a design file at the given relative path under .lexibrary/designs/."""
    design_path = project_root / ".lexibrary" / "designs" / rel_path
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text(content, encoding="utf-8")
    return design_path


def _make_lexibrary_file(project_root: Path, filename: str, content: str) -> Path:
    """Create a file directly under .lexibrary/."""
    file_path = project_root / ".lexibrary" / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path


def _make_baml_condense_mock(
    condensed_content: str,
    trimmed_sections: list[str],
) -> MagicMock:
    """Create a mock BAML CondensedFileOutput."""
    mock = MagicMock()
    mock.condensed_content = condensed_content
    mock.trimmed_sections = trimmed_sections
    return mock


# ---------------------------------------------------------------------------
# scan_token_budgets tests
# ---------------------------------------------------------------------------


class TestScanTokenBudgets:
    """Tests for the scan_token_budgets function."""

    def test_detects_over_budget_design_file(self, tmp_path: Path) -> None:
        """scan_token_budgets returns a BudgetIssue for an over-budget design file."""
        design_path = _make_design_file(
            tmp_path,
            "src/auth/login.py.md",
            "x" * 20000,  # Large content
        )
        config = CuratorConfig()

        # Set the counter to report 5000 tokens (above default 4000 limit)
        counter = FixedTokenCounter(file_counts={str(design_path): 5000})

        issues = scan_token_budgets(tmp_path, config, tokenizer=counter)

        assert len(issues) == 1
        issue = issues[0]
        assert issue.path == design_path
        assert issue.current_tokens == 5000
        assert issue.budget_target == 4000
        assert issue.file_type == "design_file"

    def test_skips_files_within_budget(self, tmp_path: Path) -> None:
        """scan_token_budgets returns empty list when all files are within budget."""
        _make_design_file(
            tmp_path,
            "src/auth/login.py.md",
            "Short content",
        )
        config = CuratorConfig()

        # Set the counter to report 500 tokens (well under 4000 limit)
        counter = FixedTokenCounter(default=500)

        issues = scan_token_budgets(tmp_path, config, tokenizer=counter)

        assert issues == []

    def test_skips_hidden_files(self, tmp_path: Path) -> None:
        """scan_token_budgets ignores files starting with '.' in the designs dir."""
        _make_design_file(
            tmp_path,
            "src/utils/.comments.yaml",
            "x" * 20000,
        )
        config = CuratorConfig()
        counter = FixedTokenCounter(default=9999)

        issues = scan_token_budgets(tmp_path, config, tokenizer=counter)

        assert issues == []

    def test_detects_over_budget_start_here(self, tmp_path: Path) -> None:
        """scan_token_budgets returns a BudgetIssue for over-budget START_HERE.md."""
        start_here = _make_lexibrary_file(
            tmp_path,
            "START_HERE.md",
            "x" * 20000,
        )
        config = CuratorConfig()

        counter = FixedTokenCounter(file_counts={str(start_here): 4000})

        issues = scan_token_budgets(tmp_path, config, tokenizer=counter)

        assert len(issues) == 1
        assert issues[0].path == start_here
        assert issues[0].file_type == "start_here"
        assert issues[0].budget_target == 3000

    def test_detects_over_budget_handoff(self, tmp_path: Path) -> None:
        """scan_token_budgets returns a BudgetIssue for over-budget HANDOFF.md."""
        handoff = _make_lexibrary_file(
            tmp_path,
            "HANDOFF.md",
            "x" * 10000,
        )
        config = CuratorConfig()

        counter = FixedTokenCounter(file_counts={str(handoff): 3000})

        issues = scan_token_budgets(tmp_path, config, tokenizer=counter)

        assert len(issues) == 1
        assert issues[0].path == handoff
        assert issues[0].file_type == "handoff"
        assert issues[0].budget_target == 2000

    def test_returns_empty_when_no_lexibrary_dir(self, tmp_path: Path) -> None:
        """scan_token_budgets returns empty list when .lexibrary/ does not exist."""
        config = CuratorConfig()
        counter = FixedTokenCounter(default=9999)

        issues = scan_token_budgets(tmp_path, config, tokenizer=counter)

        assert issues == []

    def test_custom_budget_limits(self, tmp_path: Path) -> None:
        """scan_token_budgets respects custom budget limits from config."""
        design_path = _make_design_file(
            tmp_path,
            "src/mod.py.md",
            "some content",
        )
        # Very tight budget: 200 tokens
        config = CuratorConfig(
            budget={"token_limits": {"design_file": 200}}  # type: ignore[arg-type]
        )

        counter = FixedTokenCounter(file_counts={str(design_path): 250})

        issues = scan_token_budgets(tmp_path, config, tokenizer=counter)

        assert len(issues) == 1
        assert issues[0].budget_target == 200
        assert issues[0].current_tokens == 250

    def test_multiple_over_budget_files(self, tmp_path: Path) -> None:
        """scan_token_budgets returns multiple issues for multiple over-budget files."""
        path_a = _make_design_file(tmp_path, "src/a.py.md", "content a")
        path_b = _make_design_file(tmp_path, "src/b.py.md", "content b")
        _make_design_file(tmp_path, "src/c.py.md", "content c")

        config = CuratorConfig()

        counter = FixedTokenCounter(
            file_counts={
                str(path_a): 5000,
                str(path_b): 6000,
            },
            default=100,  # c.py.md is within budget
        )

        issues = scan_token_budgets(tmp_path, config, tokenizer=counter)

        assert len(issues) == 2
        paths = {issue.path for issue in issues}
        assert path_a in paths
        assert path_b in paths

    def test_uses_approximate_tokenizer_when_none_given(self, tmp_path: Path) -> None:
        """scan_token_budgets creates an approximate tokenizer when none is provided."""
        # Write a design file with enough content to exceed the budget
        # Approximate counter: chars / 4.  4000 tokens * 4 = 16000 chars needed
        _make_design_file(
            tmp_path,
            "src/big.py.md",
            "x" * 20000,
        )
        config = CuratorConfig()

        # Don't pass a tokenizer -- should fall back to approximate
        issues = scan_token_budgets(tmp_path, config)

        # 20000 chars / 4 = 5000 tokens > 4000 budget
        assert len(issues) == 1
        assert issues[0].file_type == "design_file"

    def test_no_designs_dir(self, tmp_path: Path) -> None:
        """scan_token_budgets handles missing designs/ directory gracefully."""
        # Create .lexibrary but not designs/
        (tmp_path / ".lexibrary").mkdir()
        config = CuratorConfig()
        counter = FixedTokenCounter(default=9999)

        issues = scan_token_budgets(tmp_path, config, tokenizer=counter)

        assert issues == []


# ---------------------------------------------------------------------------
# condense_file tests (mocked BAML)
# ---------------------------------------------------------------------------


class TestCondenseFile:
    """Tests for condense_file with mocked BAML client."""

    def test_successful_condensation(self, tmp_path: Path) -> None:
        """condense_file returns CondenseResult with condensed content."""
        file_path = tmp_path / "design.md"
        file_path.write_text("# Big design file\n\nLots of content here.\n" * 100)

        issue = BudgetIssue(
            path=file_path,
            current_tokens=5000,
            budget_target=4000,
            file_type="design_file",
        )

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = _make_baml_condense_mock(
            condensed_content="# Condensed design file\n\nKey content preserved.\n",
            trimmed_sections=["Removed 5 redundant examples from Summary"],
        )

        config = CuratorConfig()
        result = asyncio.run(condense_file(issue, config, baml_client=mock_client))

        assert result.success is True
        assert result.condensed_content == "# Condensed design file\n\nKey content preserved.\n"
        assert len(result.trimmed_sections) == 1
        assert "redundant examples" in result.trimmed_sections[0]

        # Verify the BAML function was called with correct args
        mock_client.CuratorCondenseFile.assert_called_once_with(
            file_content=file_path.read_text(encoding="utf-8"),
            budget_target=4000,
            section_priority_hints=["Interface", "Dependencies", "Insights"],
        )

    def test_does_not_write_files(self, tmp_path: Path) -> None:
        """condense_file does NOT write any files -- coordinator handles writes."""
        file_path = tmp_path / "design.md"
        original_content = "# Original content\n\nSome text.\n"
        file_path.write_text(original_content)

        issue = BudgetIssue(
            path=file_path,
            current_tokens=5000,
            budget_target=4000,
            file_type="design_file",
        )

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = _make_baml_condense_mock(
            condensed_content="# Condensed\n",
            trimmed_sections=["Removed bulk"],
        )

        config = CuratorConfig()
        asyncio.run(condense_file(issue, config, baml_client=mock_client))

        # Verify the original file was NOT modified
        assert file_path.read_text(encoding="utf-8") == original_content

    def test_handles_read_error(self, tmp_path: Path) -> None:
        """condense_file returns failure when the file cannot be read."""
        # Point to a non-existent file
        issue = BudgetIssue(
            path=tmp_path / "nonexistent.md",
            current_tokens=5000,
            budget_target=4000,
            file_type="design_file",
        )

        mock_client = AsyncMock()
        config = CuratorConfig()
        result = asyncio.run(condense_file(issue, config, baml_client=mock_client))

        assert result.success is False
        assert result.condensed_content == ""
        assert result.trimmed_sections == []

        # BAML should NOT have been called
        mock_client.CuratorCondenseFile.assert_not_called()

    def test_handles_baml_error(self, tmp_path: Path) -> None:
        """condense_file returns failure when BAML call raises an exception."""
        file_path = tmp_path / "design.md"
        file_path.write_text("# Content\n")

        issue = BudgetIssue(
            path=file_path,
            current_tokens=5000,
            budget_target=4000,
            file_type="design_file",
        )

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.side_effect = RuntimeError("BAML timeout")

        config = CuratorConfig()
        result = asyncio.run(condense_file(issue, config, baml_client=mock_client))

        assert result.success is False
        assert result.condensed_content == ""
        assert result.trimmed_sections == []

    def test_uses_default_priority_hints(self, tmp_path: Path) -> None:
        """condense_file passes the default priority hints to BAML."""
        file_path = tmp_path / "design.md"
        file_path.write_text("# Content\n")

        issue = BudgetIssue(
            path=file_path,
            current_tokens=5000,
            budget_target=4000,
            file_type="design_file",
        )

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = _make_baml_condense_mock(
            condensed_content="condensed", trimmed_sections=[]
        )

        config = CuratorConfig()
        asyncio.run(condense_file(issue, config, baml_client=mock_client))

        call_kwargs = mock_client.CuratorCondenseFile.call_args
        assert call_kwargs.kwargs["section_priority_hints"] == [
            "Interface",
            "Dependencies",
            "Insights",
        ]

    def test_start_here_condensation(self, tmp_path: Path) -> None:
        """condense_file works for START_HERE.md files."""
        file_path = tmp_path / "START_HERE.md"
        file_path.write_text("# Project Overview\n\nLong overview...\n" * 50)

        issue = BudgetIssue(
            path=file_path,
            current_tokens=4000,
            budget_target=3000,
            file_type="start_here",
        )

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = _make_baml_condense_mock(
            condensed_content="# Project Overview\n\nBrief overview.\n",
            trimmed_sections=["Shortened verbose overview"],
        )

        config = CuratorConfig()
        result = asyncio.run(condense_file(issue, config, baml_client=mock_client))

        assert result.success is True
        assert "Brief overview" in result.condensed_content
