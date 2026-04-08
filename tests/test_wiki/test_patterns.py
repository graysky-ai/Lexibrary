"""Tests for lexibrary.wiki.patterns — shared wikilink regex and extraction."""

from __future__ import annotations

import re

import pytest

from lexibrary.wiki.patterns import HTML_COMMENT_RE, WIKILINK_RE, extract_wikilinks


# ---------------------------------------------------------------------------
# WIKILINK_RE tests
# ---------------------------------------------------------------------------

class TestWikilinkRE:
    """Tests for the compiled WIKILINK_RE pattern."""

    def test_basic_match(self) -> None:
        assert WIKILINK_RE.findall("[[Alpha]]") == ["Alpha"]

    def test_multiple_matches(self) -> None:
        assert WIKILINK_RE.findall("[[Alpha]] and [[Beta]]") == ["Alpha", "Beta"]

    def test_bracket_rejected(self) -> None:
        """Targets containing [ or ] must not match."""
        assert WIKILINK_RE.findall("[[invalid[x]]]") == []

    def test_embedded_in_text(self) -> None:
        text = "See [[ConceptName]] for details."
        assert WIKILINK_RE.findall(text) == ["ConceptName"]

    def test_no_match_single_brackets(self) -> None:
        assert WIKILINK_RE.findall("[NotALink]") == []

    def test_empty_brackets_no_match(self) -> None:
        assert WIKILINK_RE.findall("[[]]") == []


# ---------------------------------------------------------------------------
# HTML_COMMENT_RE tests
# ---------------------------------------------------------------------------

class TestHTMLCommentRE:
    """Tests for the compiled HTML_COMMENT_RE pattern."""

    def test_single_line_comment(self) -> None:
        result = HTML_COMMENT_RE.sub("", "before <!-- comment --> after")
        assert result == "before  after"

    def test_multi_line_comment(self) -> None:
        text = "before <!--\nmulti\nline\n--> after"
        result = HTML_COMMENT_RE.sub("", text)
        assert result == "before  after"

    def test_multiple_comments(self) -> None:
        text = "a <!-- one --> b <!-- two --> c"
        result = HTML_COMMENT_RE.sub("", text)
        assert result == "a  b  c"

    def test_no_comment(self) -> None:
        text = "no comments here"
        assert HTML_COMMENT_RE.sub("", text) == text

    def test_dotall_flag(self) -> None:
        """Verify the pattern uses DOTALL so . matches newlines."""
        assert HTML_COMMENT_RE.flags & re.DOTALL


# ---------------------------------------------------------------------------
# extract_wikilinks tests
# ---------------------------------------------------------------------------

class TestExtractWikilinks:
    """Tests for the extract_wikilinks helper function."""

    def test_basic_extraction(self) -> None:
        assert extract_wikilinks("[[Alpha]]") == ["Alpha"]

    def test_multiple_wikilinks(self) -> None:
        assert extract_wikilinks("[[Alpha]] and [[Beta]]") == ["Alpha", "Beta"]

    def test_deduplication_preserves_first_appearance(self) -> None:
        result = extract_wikilinks("[[Beta]] [[Alpha]] [[Beta]]")
        assert result == ["Beta", "Alpha"]

    def test_deduplication_multiple_repeats(self) -> None:
        result = extract_wikilinks("[[Beta]] [[Alpha]] [[Beta]] [[Alpha]]")
        assert result == ["Beta", "Alpha"]

    def test_html_comment_stripping(self) -> None:
        result = extract_wikilinks("[[A]] <!-- [[Hidden]] --> [[B]]")
        assert result == ["A", "B"]

    def test_multi_line_comment_stripping(self) -> None:
        text = "[[A]]\n<!--\n[[Hidden]]\n[[AlsoHidden]]\n-->\n[[B]]"
        result = extract_wikilinks(text)
        assert result == ["A", "B"]

    def test_whitespace_trimmed_targets(self) -> None:
        assert extract_wikilinks("[[  Padded  ]]") == ["Padded"]

    def test_empty_target_rejected(self) -> None:
        assert extract_wikilinks("[[  ]]") == []

    def test_bracket_rejected(self) -> None:
        assert extract_wikilinks("[[invalid[x]]]") == []

    def test_empty_string(self) -> None:
        assert extract_wikilinks("") == []

    def test_no_wikilinks(self) -> None:
        assert extract_wikilinks("plain text with no links") == []

    def test_mixed_valid_and_invalid(self) -> None:
        text = "[[Valid]] [[invalid[x]]] [[AlsoValid]]"
        assert extract_wikilinks(text) == ["Valid", "AlsoValid"]

    def test_comment_between_duplicates(self) -> None:
        """Wikilink inside comment should not count toward dedup."""
        text = "[[Alpha]] <!-- [[Alpha]] --> [[Alpha]]"
        result = extract_wikilinks(text)
        assert result == ["Alpha"]

    def test_adjacent_wikilinks(self) -> None:
        assert extract_wikilinks("[[A]][[B]]") == ["A", "B"]
