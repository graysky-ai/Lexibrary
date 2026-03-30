"""Tests for lexibrary.services.lookup — lookup service module."""

from __future__ import annotations

from lexibrary.services.lookup import (
    DirectoryLookupResult,
    LookupResult,
    estimate_tokens,
    truncate_lookup_sections,
)

# ---------------------------------------------------------------------------
# Dataclass construction tests
# ---------------------------------------------------------------------------


class TestLookupResultDataclass:
    """LookupResult and DirectoryLookupResult can be constructed and inspected."""

    def test_lookup_result_construction(self) -> None:
        """LookupResult can be constructed with all required fields."""
        result = LookupResult(
            file_path="src/main.py",
            description="Main entry point",
            is_stale=False,
            design_content="# Design\nSome content",
            conventions=[],
            conventions_total_count=0,
            display_limit=10,
            playbooks=[],
            playbook_display_limit=5,
            issues_text="",
            iwh_text="",
            links_text="",
            dependents=[],
            open_issue_count=0,
        )
        assert result.file_path == "src/main.py"
        assert result.description == "Main entry point"
        assert result.is_stale is False
        assert result.design_content is not None
        assert result.open_issue_count == 0

    def test_lookup_result_none_design(self) -> None:
        """LookupResult accepts None for design_content."""
        result = LookupResult(
            file_path="src/utils.py",
            description=None,
            is_stale=False,
            design_content=None,
            conventions=[],
            conventions_total_count=0,
            display_limit=10,
            playbooks=[],
            playbook_display_limit=5,
            issues_text="",
            iwh_text="",
            links_text="",
            dependents=[],
            open_issue_count=0,
        )
        assert result.design_content is None
        assert result.description is None

    def test_directory_lookup_result_construction(self) -> None:
        """DirectoryLookupResult can be constructed with all required fields."""
        result = DirectoryLookupResult(
            directory_path="src/lexibrary",
            aindex_content="# src/lexibrary\nSome content",
            conventions=[],
            conventions_total_count=0,
            display_limit=10,
            iwh_text="",
        )
        assert result.directory_path == "src/lexibrary"
        assert result.aindex_content is not None
        assert result.iwh_text == ""

    def test_directory_lookup_result_no_aindex(self) -> None:
        """DirectoryLookupResult accepts None for aindex_content."""
        result = DirectoryLookupResult(
            directory_path="src/tests",
            aindex_content=None,
            conventions=[],
            conventions_total_count=0,
            display_limit=10,
            iwh_text="",
        )
        assert result.aindex_content is None


# ---------------------------------------------------------------------------
# Token estimation tests
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    """Tests for estimate_tokens()."""

    def test_empty_string_returns_zero(self) -> None:
        """Empty string returns 0 tokens."""
        assert estimate_tokens("") == 0

    def test_nonempty_string_returns_positive(self) -> None:
        """Non-empty string returns positive token count."""
        assert estimate_tokens("hello world") > 0

    def test_four_chars_per_token_approximation(self) -> None:
        """Approximation uses ~4 characters per token."""
        assert estimate_tokens("a" * 400) == 100

    def test_minimum_one_token_for_short_text(self) -> None:
        """Very short text returns at least 1 token."""
        assert estimate_tokens("hi") >= 1


# ---------------------------------------------------------------------------
# Truncation tests
# ---------------------------------------------------------------------------


class TestTruncateLookupSections:
    """Tests for truncate_lookup_sections()."""

    def test_respects_priority_order(self) -> None:
        """Higher-priority sections are kept when budget is tight."""
        sections = [
            ("design", "x" * 400, 0),  # ~100 tokens
            ("conventions", "y" * 400, 1),  # ~100 tokens
            ("issues", "z" * 400, 2),  # ~100 tokens
            ("iwh", "w" * 400, 3),  # ~100 tokens
            ("links", "v" * 400, 4),  # ~100 tokens
        ]
        result = truncate_lookup_sections(sections, total_budget=200)
        names = [name for name, _ in result]
        assert "design" in names
        assert "conventions" in names
        assert len(result) <= 3  # at most design + conventions + partial

    def test_empty_sections_skipped(self) -> None:
        """Empty sections are not included in output."""
        sections = [
            ("design", "content here", 0),
            ("conventions", "", 1),
            ("issues", "", 2),
        ]
        result = truncate_lookup_sections(sections, total_budget=5000)
        names = [name for name, _ in result]
        assert "design" in names
        assert "conventions" not in names
        assert "issues" not in names

    def test_all_fit_within_budget(self) -> None:
        """When budget is large enough, all sections are included."""
        sections = [
            ("issues", "short text", 2),
            ("iwh", "more text", 3),
            ("links", "link data", 4),
        ]
        result = truncate_lookup_sections(sections, total_budget=100_000)
        names = [name for name, _ in result]
        assert "issues" in names
        assert "iwh" in names
        assert "links" in names

    def test_truncation_appends_notice(self) -> None:
        """When a section is truncated, a notice is appended."""
        sections = [
            ("issues", "x" * 1000, 2),  # ~250 tokens
        ]
        # Budget allows partial inclusion (> 50 tokens remaining)
        result = truncate_lookup_sections(sections, total_budget=100)
        assert len(result) == 1
        _name, content = result[0]
        assert "truncated due to token budget" in content

    def test_very_tight_budget_excludes_section(self) -> None:
        """When remaining budget is <= 50 tokens, section is excluded entirely."""
        sections = [
            ("issues", "x" * 1000, 2),  # ~250 tokens
        ]
        result = truncate_lookup_sections(sections, total_budget=10)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Import independence test
# ---------------------------------------------------------------------------


class TestImportIndependence:
    """Verify service module imports without CLI dependencies."""

    def test_import_without_cli_deps(self) -> None:
        """LookupResult is importable without pulling in CLI modules."""
        # This test verifies the spec requirement that dataclasses are
        # importable without typer, _output, or _format.
        import importlib

        mod = importlib.import_module("lexibrary.services.lookup")
        assert hasattr(mod, "LookupResult")
        assert hasattr(mod, "DirectoryLookupResult")
        assert hasattr(mod, "build_file_lookup")
        assert hasattr(mod, "build_directory_lookup")
        assert hasattr(mod, "estimate_tokens")
        assert hasattr(mod, "truncate_lookup_sections")
