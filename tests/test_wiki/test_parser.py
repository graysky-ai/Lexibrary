"""Tests for wiki concept file parser."""

from __future__ import annotations

from pathlib import Path

from lexibrary.wiki.parser import parse_concept_file

VALID_CONCEPT = """\
---
title: JWT Auth
id: CN-001
aliases:
  - JSON Web Token
tags:
  - auth
  - security
status: active
---
This concept covers authentication patterns.

See [[Rate Limiting]] and [[Session Management]] for related topics.

References `src/auth/service.py` and `src/auth/models.py` in the codebase.

## Details

JWT tokens are used for stateless authentication.

## Decision Log

- Chose RS256 over HS256 for asymmetric signing
- Refresh tokens stored in httpOnly cookies
* Added token rotation policy

## Related

More info in [[OAuth2 Flow]].
"""


class TestParseConceptFileValid:
    def test_returns_concept_file(self, tmp_path: Path) -> None:
        path = tmp_path / "JWTAuth.md"
        path.write_text(VALID_CONCEPT)
        result = parse_concept_file(path)
        assert result is not None

    def test_frontmatter_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "JWTAuth.md"
        path.write_text(VALID_CONCEPT)
        result = parse_concept_file(path)
        assert result is not None
        assert result.frontmatter.title == "JWT Auth"
        assert result.frontmatter.aliases == ["JSON Web Token"]
        assert result.frontmatter.tags == ["auth", "security"]
        assert result.frontmatter.status == "active"
        assert result.frontmatter.superseded_by is None

    def test_summary_extraction(self, tmp_path: Path) -> None:
        path = tmp_path / "JWTAuth.md"
        path.write_text(VALID_CONCEPT)
        result = parse_concept_file(path)
        assert result is not None
        assert result.summary == "This concept covers authentication patterns."

    def test_wikilink_extraction(self, tmp_path: Path) -> None:
        path = tmp_path / "JWTAuth.md"
        path.write_text(VALID_CONCEPT)
        result = parse_concept_file(path)
        assert result is not None
        assert "Rate Limiting" in result.related_concepts
        assert "Session Management" in result.related_concepts
        assert "OAuth2 Flow" in result.related_concepts

    def test_file_reference_extraction(self, tmp_path: Path) -> None:
        path = tmp_path / "JWTAuth.md"
        path.write_text(VALID_CONCEPT)
        result = parse_concept_file(path)
        assert result is not None
        assert "src/auth/service.py" in result.linked_files
        assert "src/auth/models.py" in result.linked_files

    def test_decision_log_extraction(self, tmp_path: Path) -> None:
        path = tmp_path / "JWTAuth.md"
        path.write_text(VALID_CONCEPT)
        result = parse_concept_file(path)
        assert result is not None
        assert len(result.decision_log) == 3
        assert "Chose RS256 over HS256 for asymmetric signing" in result.decision_log
        assert "Added token rotation policy" in result.decision_log

    def test_body_preserved(self, tmp_path: Path) -> None:
        path = tmp_path / "JWTAuth.md"
        path.write_text(VALID_CONCEPT)
        result = parse_concept_file(path)
        assert result is not None
        assert "## Details" in result.body
        assert "## Decision Log" in result.body


class TestParseConceptFileEdgeCases:
    def test_nonexistent_file(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.md"
        assert parse_concept_file(path) is None

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        path = tmp_path / "nofm.md"
        path.write_text("# Just a heading\n\nSome text.\n")
        assert parse_concept_file(path) is None

    def test_invalid_frontmatter_missing_title(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.md"
        path.write_text("---\naliases: []\ntags: []\n---\nBody.\n")
        assert parse_concept_file(path) is None

    def test_invalid_frontmatter_bad_status(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.md"
        path.write_text("---\ntitle: Test\nid: CN-001\nstatus: unknown\n---\nBody.\n")
        assert parse_concept_file(path) is None

    def test_empty_body(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.md"
        path.write_text("---\ntitle: Empty\nid: CN-002\n---\n")
        result = parse_concept_file(path)
        assert result is not None
        assert result.summary == ""
        assert result.related_concepts == []
        assert result.linked_files == []
        assert result.decision_log == []

    def test_no_wikilinks(self, tmp_path: Path) -> None:
        path = tmp_path / "nolinks.md"
        path.write_text("---\ntitle: Plain\nid: CN-003\n---\nJust plain text.\n")
        result = parse_concept_file(path)
        assert result is not None
        assert result.related_concepts == []

    def test_no_decision_log_section(self, tmp_path: Path) -> None:
        path = tmp_path / "nodeclog.md"
        path.write_text("---\ntitle: NoDL\nid: CN-004\n---\n## Details\n\nSome details.\n")
        result = parse_concept_file(path)
        assert result is not None
        assert result.decision_log == []

    def test_summary_before_first_heading(self, tmp_path: Path) -> None:
        path = tmp_path / "summ.md"
        path.write_text(
            "---\ntitle: Summ\nid: CN-005\n---\nFirst paragraph.\n\n## Heading\n\nMore.\n"
        )
        result = parse_concept_file(path)
        assert result is not None
        assert result.summary == "First paragraph."


class TestParseConceptFileHtmlComments:
    def test_wikilinks_inside_html_comments_ignored(self, tmp_path: Path) -> None:
        """Wikilinks inside HTML comments are not extracted as related concepts."""
        content = (
            "---\n"
            "title: CommentTest\n"
            "id: CN-010\n"
            "status: active\n"
            "---\n"
            "<!-- [[Hidden]] -->\n"
            "See [[Visible]] for details.\n"
        )
        path = tmp_path / "comment_test.md"
        path.write_text(content)
        result = parse_concept_file(path)
        assert result is not None
        assert "Visible" in result.related_concepts
        assert "Hidden" not in result.related_concepts

    def test_body_preserves_html_comments(self, tmp_path: Path) -> None:
        """The body field retains HTML comments even though wikilink extraction strips them."""
        content = (
            "---\n"
            "title: BodyPreserve\n"
            "id: CN-011\n"
            "status: active\n"
            "---\n"
            "<!-- keep this comment -->\n"
            "Some text with [[Visible]].\n"
        )
        path = tmp_path / "body_preserve.md"
        path.write_text(content)
        result = parse_concept_file(path)
        assert result is not None
        assert "<!-- keep this comment -->" in result.body
