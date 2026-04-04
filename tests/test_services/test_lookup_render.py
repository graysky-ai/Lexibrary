"""Tests for lexibrary.services.lookup_render — render functions for lookup results."""

from __future__ import annotations

from lexibrary.services.lookup import ConceptSummary, SiblingSummary
from lexibrary.services.lookup_render import (
    render_directory_link_summary,
    render_related_concepts,
    render_siblings,
)

# ---------------------------------------------------------------------------
# 6.6 — render_siblings()
# ---------------------------------------------------------------------------


class TestRenderSiblings:
    """Tests for render_siblings() brief and full modes."""

    def test_brief_mode_inline_list(self) -> None:
        """Brief mode returns comma-separated inline list."""
        siblings = [
            SiblingSummary(name="a.py", description="Module A"),
            SiblingSummary(name="b.py", description="Module B"),
            SiblingSummary(name="c.py", description="Module C"),
        ]
        result = render_siblings(siblings, "src/pkg/b.py", full=False)
        assert result.startswith("Siblings: ")
        assert "a.py" in result
        assert "b.py (this file)" in result
        assert "c.py" in result
        assert result.endswith("\n")

    def test_brief_mode_this_file_marker(self) -> None:
        """Brief mode marks the current file with '(this file)'."""
        siblings = [
            SiblingSummary(name="current.py", description="Current module"),
            SiblingSummary(name="other.py", description="Other module"),
        ]
        result = render_siblings(siblings, "src/pkg/current.py", full=False)
        assert "current.py (this file)" in result
        # "other.py" should NOT have the marker
        assert "other.py (this file)" not in result
        assert "other.py" in result

    def test_full_mode_heading_and_descriptions(self) -> None:
        """Full mode returns '## Sibling Files' section with descriptions."""
        siblings = [
            SiblingSummary(name="main.py", description="Main entry point"),
            SiblingSummary(name="utils.py", description="Utility functions"),
        ]
        result = render_siblings(siblings, "src/pkg/main.py", full=True)
        assert "## Sibling Files" in result
        assert "main.py (this file) -- Main entry point" in result
        assert "utils.py -- Utility functions" in result

    def test_full_mode_this_file_marker(self) -> None:
        """Full mode marks the current file with '(this file)'."""
        siblings = [
            SiblingSummary(name="target.py", description="Target"),
            SiblingSummary(name="other.py", description="Other"),
        ]
        result = render_siblings(siblings, "src/pkg/target.py", full=True)
        assert "target.py (this file)" in result
        assert "other.py (this file)" not in result

    def test_empty_list_returns_empty_string(self) -> None:
        """Empty siblings list returns empty string."""
        result = render_siblings([], "src/foo.py", full=False)
        assert result == ""

        result = render_siblings([], "src/foo.py", full=True)
        assert result == ""

    def test_non_sibling_objects_filtered(self) -> None:
        """Non-SiblingSummary objects are filtered out."""
        result = render_siblings(["not a sibling"], "src/foo.py", full=False)
        assert result == ""


# ---------------------------------------------------------------------------
# 6.7 — render_related_concepts()
# ---------------------------------------------------------------------------


class TestRenderRelatedConcepts:
    """Tests for render_related_concepts() brief and full modes."""

    def test_brief_mode_inline_with_status(self) -> None:
        """Brief mode returns inline list with [[name]] (status) format."""
        concepts = [
            ConceptSummary(name="error-handling", status="active", summary=None),
            ConceptSummary(name="logging", status="draft", summary=None),
        ]
        result = render_related_concepts(concepts, full=False)
        assert result.startswith("Related concepts: ")
        assert "[[error-handling]] (active)" in result
        assert "[[logging]] (draft)" in result
        assert result.endswith("\n")

    def test_brief_mode_no_parenthetical_when_status_none(self) -> None:
        """Brief mode omits status parenthetical when status is None."""
        concepts = [
            ConceptSummary(name="unknown-concept", status=None, summary=None),
        ]
        result = render_related_concepts(concepts, full=False)
        assert "[[unknown-concept]]" in result
        # No parenthetical after the name
        assert "[[unknown-concept]] (" not in result

    def test_brief_mode_mixed_status(self) -> None:
        """Brief mode handles mix of known and unknown statuses."""
        concepts = [
            ConceptSummary(name="known", status="active", summary=None),
            ConceptSummary(name="unknown", status=None, summary=None),
        ]
        result = render_related_concepts(concepts, full=False)
        assert "[[known]] (active)" in result
        assert "[[unknown]]" in result
        # The unknown one should not have a parenthetical
        parts = result.split("[[unknown]]")
        assert len(parts) == 2
        # After [[unknown]], next char should be comma or newline, not " ("
        after_unknown = parts[1].lstrip()
        assert not after_unknown.startswith("(")

    def test_full_mode_heading_and_summaries(self) -> None:
        """Full mode returns '## Related Concepts' section with summaries."""
        concepts = [
            ConceptSummary(name="error-handling", status="active", summary="Error patterns"),
            ConceptSummary(name="logging", status="draft", summary="Logging approach"),
        ]
        result = render_related_concepts(concepts, full=True)
        assert "## Related Concepts" in result
        assert "**error-handling** (active) -- Error patterns" in result
        assert "**logging** (draft) -- Logging approach" in result

    def test_full_mode_linkgraph_unavailable_heading(self) -> None:
        """Full mode with linkgraph_available=False shows altered heading."""
        concepts = [
            ConceptSummary(name="my-concept", status=None, summary=None),
        ]
        result = render_related_concepts(concepts, full=True, linkgraph_available=False)
        assert "## Related Concepts (link graph unavailable -- names only)" in result

    def test_full_mode_no_summary(self) -> None:
        """Full mode omits dash-separated summary when summary is None."""
        concepts = [
            ConceptSummary(name="sparse", status="active", summary=None),
        ]
        result = render_related_concepts(concepts, full=True)
        assert "**sparse** (active)" in result
        # Should not have " -- " after status
        assert "**sparse** (active) --" not in result

    def test_empty_list_returns_empty_string(self) -> None:
        """Empty concepts list returns empty string."""
        result = render_related_concepts([], full=False)
        assert result == ""

        result = render_related_concepts([], full=True)
        assert result == ""

    def test_non_concept_objects_filtered(self) -> None:
        """Non-ConceptSummary objects are filtered out."""
        result = render_related_concepts(["not a concept"], full=False)
        assert result == ""


# ---------------------------------------------------------------------------
# 6.8 — render_directory_link_summary()
# ---------------------------------------------------------------------------


class TestRenderDirectoryLinkSummary:
    """Tests for render_directory_link_summary()."""

    def test_positive_counts_returns_formatted_line(self) -> None:
        """Counts > 0 returns formatted inbound imports line."""
        result = render_directory_link_summary(import_count=15, imported_file_count=7)
        assert result == "Inbound imports: 15 (across 7 files)\n"

    def test_single_count_single_file(self) -> None:
        """Single import from single file."""
        result = render_directory_link_summary(import_count=1, imported_file_count=1)
        assert result == "Inbound imports: 1 (across 1 files)\n"

    def test_zero_count_returns_empty_string(self) -> None:
        """import_count == 0 returns empty string."""
        result = render_directory_link_summary(import_count=0, imported_file_count=0)
        assert result == ""

    def test_zero_import_count_ignores_file_count(self) -> None:
        """Zero import_count returns empty string regardless of file count."""
        result = render_directory_link_summary(import_count=0, imported_file_count=5)
        assert result == ""
