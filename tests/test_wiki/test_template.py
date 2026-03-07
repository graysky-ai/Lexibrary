"""Tests for wiki concept file template rendering and path derivation."""

from __future__ import annotations

from pathlib import Path

from lexibrary.wiki.template import concept_file_path, render_concept_template


class TestRenderConceptTemplate:
    def test_name_only(self) -> None:
        result = render_concept_template("JWT Auth")
        assert "title: JWT Auth" in result
        assert "status: active" in result
        assert "tags: []" in result
        assert "aliases: []" in result
        assert "## Details" in result
        assert "## Decision Log" in result
        assert "## Related" in result
        assert "<!-- add [[wikilinks]] here -->" in result

    def test_with_tags(self) -> None:
        result = render_concept_template("JWT Auth", tags=["auth", "security"])
        assert "auth" in result
        assert "security" in result

    def test_starts_with_frontmatter(self) -> None:
        result = render_concept_template("Test")
        assert result.startswith("---\n")
        # Has closing frontmatter delimiter
        lines = result.splitlines()
        assert "---" in lines[0]

    def test_no_tags_defaults_to_empty(self) -> None:
        result = render_concept_template("Test")
        assert "tags: []" in result


class TestConceptFilePath:
    def test_simple_name(self) -> None:
        result = concept_file_path("JWT Auth", Path(".lexibrary/concepts"))
        assert result == Path(".lexibrary/concepts/JwtAuth.md")

    def test_special_characters_stripped(self) -> None:
        result = concept_file_path("Rate Limiting (API)", Path(".lexibrary/concepts"))
        assert result == Path(".lexibrary/concepts/RateLimitingApi.md")

    def test_single_word(self) -> None:
        result = concept_file_path("Auth", Path(".lexibrary/concepts"))
        assert result == Path(".lexibrary/concepts/Auth.md")

    def test_hyphenated_name(self) -> None:
        result = concept_file_path("rate-limiting", Path(".lexibrary/concepts"))
        assert result == Path(".lexibrary/concepts/RateLimiting.md")

    def test_custom_directory(self) -> None:
        result = concept_file_path("Test", Path("/custom/dir"))
        assert result == Path("/custom/dir/Test.md")
