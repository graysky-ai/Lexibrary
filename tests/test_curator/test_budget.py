"""Tests for Phase 3: Budget Trimmer sub-agent.

Covers:
- scan_token_budgets detects over-budget design files
- scan_token_budgets skips files within budget
- scan_token_budgets detects over-budget START_HERE.md and HANDOFF.md
- condense_file (standalone, post curator-4 extraction) runs BAML and
  writes the condensed body atomically with updated_by="archivist"
- condense_file refreshes source_hash / interface_hash from source
- condense_file raises RuntimeError when BAML fails or produces an
  unparseable body

Note: the standalone ``condense_file`` introduced by ``curator-4``
Phase 4 replaced the earlier BAML-wrapper-only function of the same
name.  The earlier behaviour lives on as the private
``_call_baml_condense`` helper; the tests here exercise the new public
signature.  Additional coverage lives in
``tests/test_curator/test_condense_file_helper.py``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from unittest.mock import AsyncMock, MagicMock

import pytest

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.budget import (
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
# condense_file tests (standalone helper — curator-4 Phase 4 extraction)
# ---------------------------------------------------------------------------
#
# The ``condense_file`` public signature changed in curator-4: it now
# takes ``(design_path, project_root, config)``, runs BAML, and writes
# the condensed body atomically.  The in-flight BAML output tests moved
# to ``tests/test_curator/test_condense_file_helper.py``; the tests
# below keep the legacy sub-agent coverage alive against the new
# signature so ``pytest tests/test_curator/test_budget*`` remains the
# "budget sub-agent smoke suite" it was before the extraction.


def _write_design_fixture(
    project_root: Path,
    source_rel: str,
    *,
    body_seed: str = "Summary paragraph for the fixture design file.\n",
) -> Path:
    """Build a minimal valid design file on disk and return its Path.

    Creates a matching stub source file so :func:`compute_hashes` does
    not raise during :func:`condense_file` hash refresh.
    """
    source_abs = project_root / source_rel
    source_abs.parent.mkdir(parents=True, exist_ok=True)
    source_abs.write_text("def noop() -> None:\n    return None\n", encoding="utf-8")

    design_path = project_root / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Budget test fixture.",
            id="DS-BUDGET-TEST",
            updated_by="agent",
        ),
        summary=body_seed,
        interface_contract="def noop() -> None: ...",
        dependencies=[],
        dependents=[],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="stale-source-hash",
            interface_hash="stale-interface-hash",
            design_hash="stale-design-hash",
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="test",
        ),
    )
    design_path.write_text(serialize_design_file(df), encoding="utf-8")
    return design_path


def _condensed_fixture_body(source_rel: str) -> str:
    """Return a serialised design body for the BAML mock to 'produce'."""
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Condensed fixture.",
            id="DS-BUDGET-TEST",
            updated_by="curator",  # will be flipped to archivist by helper
        ),
        summary="Condensed summary.",
        interface_contract="def noop() -> None: ...",
        dependencies=[],
        dependents=[],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="baml-source-hash",
            interface_hash="baml-interface-hash",
            design_hash="baml-design-hash",
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="test",
        ),
    )
    return serialize_design_file(df)


class TestCondenseFile:
    """Sub-agent-level smoke tests against the new ``condense_file`` signature."""

    def test_successful_condensation_writes_and_updates_authorship(self, tmp_path: Path) -> None:
        """condense_file writes condensed body with updated_by=archivist."""
        source_rel = "src/mod.py"
        design_path = _write_design_fixture(tmp_path, source_rel)
        condensed_body = _condensed_fixture_body(source_rel)

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = _make_baml_condense_mock(
            condensed_content=condensed_body,
            trimmed_sections=["Removed verbose examples"],
        )

        config = LexibraryConfig()
        result = asyncio.run(condense_file(design_path, tmp_path, config, baml_client=mock_client))

        # CondenseResult carries before/after plus trimmed manifest.
        assert result.before_tokens > 0
        assert result.after_tokens > 0
        assert result.trimmed_sections == ["Removed verbose examples"]

        # Post-write: frontmatter updated_by flipped to archivist.
        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.frontmatter.updated_by == "archivist"

    def test_handles_baml_error_raises(self, tmp_path: Path) -> None:
        """condense_file raises RuntimeError when the BAML call fails."""
        source_rel = "src/mod.py"
        design_path = _write_design_fixture(tmp_path, source_rel)

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.side_effect = RuntimeError("BAML timeout")

        config = LexibraryConfig()
        with pytest.raises(RuntimeError):
            asyncio.run(condense_file(design_path, tmp_path, config, baml_client=mock_client))

    def test_uses_default_priority_hints(self, tmp_path: Path) -> None:
        """condense_file passes the default priority hints to BAML."""
        source_rel = "src/mod.py"
        design_path = _write_design_fixture(tmp_path, source_rel)
        condensed_body = _condensed_fixture_body(source_rel)

        mock_client = AsyncMock()
        mock_client.CuratorCondenseFile.return_value = _make_baml_condense_mock(
            condensed_content=condensed_body, trimmed_sections=[]
        )

        config = LexibraryConfig()
        asyncio.run(condense_file(design_path, tmp_path, config, baml_client=mock_client))

        call_kwargs = mock_client.CuratorCondenseFile.call_args
        assert call_kwargs.kwargs["section_priority_hints"] == [
            "Interface",
            "Dependencies",
            "Insights",
        ]
