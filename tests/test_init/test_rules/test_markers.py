"""Tests for init/rules/markers.py — marker-based section utilities."""

from __future__ import annotations

from lexibrary.init.rules.markers import (
    MARKER_END,
    MARKER_START,
    append_lexibrary_section,
    has_lexibrary_section,
    replace_lexibrary_section,
)

# ---------------------------------------------------------------------------
# Marker constants
# ---------------------------------------------------------------------------


def test_marker_start_value() -> None:
    """MARKER_START is the expected HTML comment."""
    assert MARKER_START == "<!-- lexibrary:start -->"


def test_marker_end_value() -> None:
    """MARKER_END is the expected HTML comment."""
    assert MARKER_END == "<!-- lexibrary:end -->"


# ---------------------------------------------------------------------------
# has_lexibrary_section — detection
# ---------------------------------------------------------------------------


def test_detects_both_markers_present() -> None:
    """Returns True when both start and end markers are present."""
    content = f"Some preamble\n{MARKER_START}\nrules here\n{MARKER_END}\npostamble"
    assert has_lexibrary_section(content) is True


def test_no_markers_returns_false() -> None:
    """Returns False when neither marker is present."""
    content = "# My CLAUDE.md\n\nNo lexibrary section here.\n"
    assert has_lexibrary_section(content) is False


def test_only_start_marker_returns_false() -> None:
    """Returns False when only the start marker is present."""
    content = f"Preamble\n{MARKER_START}\nrules here but no end marker\n"
    assert has_lexibrary_section(content) is False


def test_only_end_marker_returns_false() -> None:
    """Returns False when only the end marker is present."""
    content = f"Preamble\nrules here\n{MARKER_END}\n"
    assert has_lexibrary_section(content) is False


def test_empty_content_returns_false() -> None:
    """Returns False for empty string."""
    assert has_lexibrary_section("") is False


def test_detects_markers_with_empty_section() -> None:
    """Returns True when markers are present but section body is empty."""
    content = f"{MARKER_START}\n{MARKER_END}"
    assert has_lexibrary_section(content) is True


# ---------------------------------------------------------------------------
# replace_lexibrary_section — replacement
# ---------------------------------------------------------------------------


def test_replaces_content_between_markers() -> None:
    """Replaces old section content with new section."""
    original = f"Preamble\n{MARKER_START}\nold rules\n{MARKER_END}\nPostamble"
    result = replace_lexibrary_section(original, "new rules")
    assert "old rules" not in result
    assert "new rules" in result
    assert MARKER_START in result
    assert MARKER_END in result


def test_surrounding_content_preserved() -> None:
    """Content before and after the marker block remains unchanged."""
    preamble = "# My Project Rules\n\nDo not touch this."
    postamble = "\n## My Custom Section\n\nAlso preserved."
    original = f"{preamble}\n{MARKER_START}\nold stuff\n{MARKER_END}{postamble}"
    result = replace_lexibrary_section(original, "updated rules")
    assert result.startswith(preamble)
    assert result.endswith(postamble)


def test_handles_whitespace_around_markers() -> None:
    """Replacement succeeds when extra blank lines surround markers."""
    original = (
        f"Preamble\n\n{MARKER_START}\n\n  old rules with whitespace  \n\n{MARKER_END}\n\nPostamble"
    )
    result = replace_lexibrary_section(original, "clean rules")
    assert "clean rules" in result
    assert "old rules" not in result
    assert "Preamble" in result
    assert "Postamble" in result


def test_replaces_multiline_section() -> None:
    """Correctly replaces a multi-line section between markers."""
    original = f"{MARKER_START}\nline 1\nline 2\nline 3\n{MARKER_END}"
    result = replace_lexibrary_section(original, "single line")
    assert result == f"{MARKER_START}\nsingle line\n{MARKER_END}"


def test_replacement_wraps_in_markers() -> None:
    """The replacement output has markers around the new content."""
    original = f"{MARKER_START}\nold\n{MARKER_END}"
    result = replace_lexibrary_section(original, "new")
    expected = f"{MARKER_START}\nnew\n{MARKER_END}"
    assert result == expected


# ---------------------------------------------------------------------------
# append_lexibrary_section — append
# ---------------------------------------------------------------------------


def test_appends_to_existing_content() -> None:
    """Appends marker-delimited section after existing content."""
    existing = "# My Rules\n\nDo things properly."
    result = append_lexibrary_section(existing, "lexi rules")
    assert result.startswith("# My Rules")
    assert MARKER_START in result
    assert "lexi rules" in result
    assert MARKER_END in result
    # Marker section should come after existing content
    assert result.index("# My Rules") < result.index(MARKER_START)


def test_appends_to_empty_content() -> None:
    """Appending to empty content returns just the marker block."""
    result = append_lexibrary_section("", "lexi rules")
    expected = f"{MARKER_START}\nlexi rules\n{MARKER_END}"
    assert result == expected


def test_append_has_blank_line_separator() -> None:
    """A blank line separates existing content from the appended section."""
    existing = "Line one"
    result = append_lexibrary_section(existing, "rules")
    # Should have double newline between existing and markers
    assert f"Line one\n\n{MARKER_START}" in result


def test_append_strips_trailing_newlines() -> None:
    """Trailing newlines on existing content are normalised before appending."""
    existing = "Content\n\n\n"
    result = append_lexibrary_section(existing, "rules")
    # Should collapse trailing newlines to exactly one blank-line separator
    assert f"Content\n\n{MARKER_START}" in result


def test_append_result_has_both_markers() -> None:
    """Appended section always has matching start and end markers."""
    result = append_lexibrary_section("stuff", "new section")
    assert has_lexibrary_section(result) is True


def test_append_with_multiline_new_section() -> None:
    """Appending a multi-line section wraps it correctly."""
    multi_line = "rule 1\nrule 2\nrule 3"
    result = append_lexibrary_section("", multi_line)
    expected = f"{MARKER_START}\nrule 1\nrule 2\nrule 3\n{MARKER_END}"
    assert result == expected
