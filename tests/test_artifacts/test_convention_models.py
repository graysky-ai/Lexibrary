"""Tests for convention artifact Pydantic 2 data models and slug/path helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from lexibrary.artifacts.convention import (
    ConventionFile,
    ConventionFileFrontmatter,
    convention_file_path,
    convention_slug,
)

# ---------------------------------------------------------------------------
# ConventionFileFrontmatter
# ---------------------------------------------------------------------------


class TestConventionFileFrontmatter:
    def test_defaults(self) -> None:
        fm = ConventionFileFrontmatter(title="Use UTC everywhere")
        assert fm.title == "Use UTC everywhere"
        assert fm.scope == "project"
        assert fm.tags == []
        assert fm.status == "draft"
        assert fm.source == "user"
        assert fm.priority == 0

    def test_all_fields(self) -> None:
        fm = ConventionFileFrontmatter(
            title="Future annotations",
            scope="project",
            tags=["python"],
            status="active",
            source="config",
            priority=10,
        )
        assert fm.title == "Future annotations"
        assert fm.scope == "project"
        assert fm.tags == ["python"]
        assert fm.status == "active"
        assert fm.source == "config"
        assert fm.priority == 10

    def test_directory_scope(self) -> None:
        fm = ConventionFileFrontmatter(title="Test", scope="src/auth")
        assert fm.scope == "src/auth"

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConventionFileFrontmatter(title="Bad", status="archived")  # type: ignore[arg-type]

    def test_invalid_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConventionFileFrontmatter(title="Bad", source="llm")  # type: ignore[arg-type]

    def test_all_valid_statuses(self) -> None:
        for status in ("draft", "active", "deprecated"):
            fm = ConventionFileFrontmatter(title="Test", status=status)  # type: ignore[arg-type]
            assert fm.status == status

    def test_all_valid_sources(self) -> None:
        for source in ("user", "agent", "config"):
            fm = ConventionFileFrontmatter(title="Test", source=source)  # type: ignore[arg-type]
            assert fm.source == source


# ---------------------------------------------------------------------------
# ConventionFile
# ---------------------------------------------------------------------------


class TestConventionFile:
    def test_minimal_valid(self) -> None:
        fm = ConventionFileFrontmatter(title="Test")
        cf = ConventionFile(frontmatter=fm, body="")
        assert cf.rule == ""
        assert cf.file_path is None

    def test_name_property(self) -> None:
        fm = ConventionFileFrontmatter(title="Use UTC everywhere")
        cf = ConventionFile(frontmatter=fm)
        assert cf.name == "Use UTC everywhere"

    def test_scope_property(self) -> None:
        fm = ConventionFileFrontmatter(title="Test", scope="src/auth")
        cf = ConventionFile(frontmatter=fm)
        assert cf.scope == "src/auth"

    def test_rule_extraction_stored(self) -> None:
        fm = ConventionFileFrontmatter(title="Test")
        cf = ConventionFile(
            frontmatter=fm,
            body="Every module must use X.\n\n**Rationale**: Because Y.",
            rule="Every module must use X.",
        )
        assert cf.rule == "Every module must use X."

    def test_file_path_stored(self) -> None:
        fm = ConventionFileFrontmatter(title="Test")
        p = Path("/tmp/conventions/test.md")
        cf = ConventionFile(frontmatter=fm, file_path=p)
        assert cf.file_path == p

    def test_importable_from_artifacts(self) -> None:
        from lexibrary.artifacts import ConventionFile, ConventionFileFrontmatter

        assert ConventionFile is not None
        assert ConventionFileFrontmatter is not None


# ---------------------------------------------------------------------------
# convention_slug
# ---------------------------------------------------------------------------


class TestConventionSlug:
    def test_simple_title(self) -> None:
        assert convention_slug("Future annotations import") == "future-annotations-import"

    def test_special_characters(self) -> None:
        assert convention_slug("Use `from __future__` import") == "use-from-future-import"

    def test_already_kebab(self) -> None:
        assert convention_slug("already-kebab-case") == "already-kebab-case"

    def test_leading_trailing_special(self) -> None:
        assert convention_slug("  --Hello World--  ") == "hello-world"

    def test_consecutive_special_chars(self) -> None:
        assert convention_slug("Use --- dashes & ampersands") == "use-dashes-ampersands"

    def test_long_title_truncation(self) -> None:
        long_title = (
            "This is a very long convention title that exceeds"
            " the sixty character limit by a significant margin"
        )
        slug = convention_slug(long_title)
        assert len(slug) <= 60
        # Should not end with a hyphen
        assert not slug.endswith("-")

    def test_long_title_truncates_at_word_boundary(self) -> None:
        # 60 chars of slug would split a word; should truncate at last hyphen
        long_title = "a b c d e f g h i j k l m n o p q r s t u v w x y z alpha beta gamma delta"
        slug = convention_slug(long_title)
        assert len(slug) <= 60
        # The slug should be a valid kebab string (no trailing hyphens)
        assert not slug.endswith("-")

    def test_empty_after_strip(self) -> None:
        # Edge case: title of only special characters
        slug = convention_slug("---")
        assert slug == ""

    def test_single_word(self) -> None:
        assert convention_slug("TypeScript") == "typescript"


# ---------------------------------------------------------------------------
# convention_file_path
# ---------------------------------------------------------------------------


class TestConventionFilePath:
    def test_no_collision(self, tmp_path: Path) -> None:
        result = convention_file_path("Use UTC", tmp_path)
        assert result == tmp_path / "use-utc.md"

    def test_collision_appends_suffix(self, tmp_path: Path) -> None:
        (tmp_path / "use-utc.md").write_text("existing")
        result = convention_file_path("Use UTC", tmp_path)
        assert result == tmp_path / "use-utc-2.md"

    def test_multiple_collisions(self, tmp_path: Path) -> None:
        (tmp_path / "use-utc.md").write_text("existing")
        (tmp_path / "use-utc-2.md").write_text("existing")
        (tmp_path / "use-utc-3.md").write_text("existing")
        result = convention_file_path("Use UTC", tmp_path)
        assert result == tmp_path / "use-utc-4.md"
