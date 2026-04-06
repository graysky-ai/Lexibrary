"""Tests for convention artifact Pydantic 2 data models and slug/path helpers."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from lexibrary.artifacts.convention import (
    ConventionFile,
    ConventionFileFrontmatter,
    convention_file_path,
    convention_slug,
    split_scope,
)

# ---------------------------------------------------------------------------
# ConventionFileFrontmatter
# ---------------------------------------------------------------------------


class TestConventionFileFrontmatter:
    def test_defaults(self) -> None:
        fm = ConventionFileFrontmatter(title="Use UTC everywhere", id="CV-001")
        assert fm.title == "Use UTC everywhere"
        assert fm.scope == "project"
        assert fm.tags == []
        assert fm.status == "draft"
        assert fm.source == "user"
        assert fm.priority == 0
        assert fm.aliases == []
        assert fm.deprecated_at is None

    def test_all_fields(self) -> None:
        fm = ConventionFileFrontmatter(
            title="Future annotations",
            id="CV-001",
            scope="project",
            tags=["python"],
            aliases=["future-annotations"],
            status="deprecated",
            source="config",
            priority=10,
            deprecated_at="2026-03-04T10:00:00",
        )
        assert fm.title == "Future annotations"
        assert fm.scope == "project"
        assert fm.tags == ["python"]
        assert fm.aliases == ["future-annotations"]
        assert fm.status == "deprecated"
        assert fm.source == "config"
        assert fm.priority == 10
        assert fm.deprecated_at == datetime(2026, 3, 4, 10, 0, 0)

    def test_aliases_default_empty(self) -> None:
        fm = ConventionFileFrontmatter(title="Test", id="CV-001")
        assert fm.aliases == []

    def test_aliases_multiple(self) -> None:
        fm = ConventionFileFrontmatter(
            title="Auth decorator required",
            id="CV-001",
            aliases=["auth-decorator", "auth-conv"],
        )
        assert fm.aliases == ["auth-decorator", "auth-conv"]

    def test_deprecated_at_defaults_to_none(self) -> None:
        fm = ConventionFileFrontmatter(title="Test", id="CV-001", status="active")
        assert fm.deprecated_at is None

    def test_deprecated_at_with_timestamp(self) -> None:
        fm = ConventionFileFrontmatter(
            title="Old rule",
            id="CV-001",
            status="deprecated",
            deprecated_at="2026-03-04T10:00:00",
        )
        assert fm.deprecated_at == datetime(2026, 3, 4, 10, 0, 0)

    def test_directory_scope(self) -> None:
        fm = ConventionFileFrontmatter(title="Test", id="CV-001", scope="src/auth")
        assert fm.scope == "src/auth"

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConventionFileFrontmatter(title="Bad", id="CV-001", status="archived")  # type: ignore[arg-type]

    def test_invalid_source_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConventionFileFrontmatter(title="Bad", id="CV-001", source="llm")  # type: ignore[arg-type]

    def test_all_valid_statuses(self) -> None:
        for status in ("draft", "active", "deprecated"):
            fm = ConventionFileFrontmatter(title="Test", id="CV-001", status=status)  # type: ignore[arg-type]
            assert fm.status == status

    def test_all_valid_sources(self) -> None:
        for source in ("user", "agent", "config"):
            fm = ConventionFileFrontmatter(title="Test", id="CV-001", source=source)  # type: ignore[arg-type]
            assert fm.source == source


# ---------------------------------------------------------------------------
# ConventionFile
# ---------------------------------------------------------------------------


class TestConventionFile:
    def test_minimal_valid(self) -> None:
        fm = ConventionFileFrontmatter(title="Test", id="CV-001")
        cf = ConventionFile(frontmatter=fm, body="")
        assert cf.rule == ""
        assert cf.file_path is None

    def test_name_property(self) -> None:
        fm = ConventionFileFrontmatter(title="Use UTC everywhere", id="CV-001")
        cf = ConventionFile(frontmatter=fm)
        assert cf.name == "Use UTC everywhere"

    def test_scope_property(self) -> None:
        fm = ConventionFileFrontmatter(title="Test", id="CV-001", scope="src/auth")
        cf = ConventionFile(frontmatter=fm)
        assert cf.scope == "src/auth"

    def test_scope_paths_single(self) -> None:
        fm = ConventionFileFrontmatter(title="Test", id="CV-001", scope="src/auth")
        cf = ConventionFile(frontmatter=fm)
        assert cf.scope_paths == ["src/auth"]

    def test_scope_paths_multi(self) -> None:
        fm = ConventionFileFrontmatter(
            title="Test", id="CV-001", scope="src/cli/, src/services/"
        )
        cf = ConventionFile(frontmatter=fm)
        assert cf.scope_paths == ["src/cli", "src/services"]

    def test_scope_paths_project(self) -> None:
        fm = ConventionFileFrontmatter(title="Test", id="CV-001", scope="project")
        cf = ConventionFile(frontmatter=fm)
        assert cf.scope_paths == ["project"]

    def test_rule_extraction_stored(self) -> None:
        fm = ConventionFileFrontmatter(title="Test", id="CV-001")
        cf = ConventionFile(
            frontmatter=fm,
            body="Every module must use X.\n\n**Rationale**: Because Y.",
            rule="Every module must use X.",
        )
        assert cf.rule == "Every module must use X."

    def test_file_path_stored(self) -> None:
        fm = ConventionFileFrontmatter(title="Test", id="CV-001")
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
    def test_id_prefixed_path(self, tmp_path: Path) -> None:
        result = convention_file_path("CV-001", "Use UTC", tmp_path)
        assert result == tmp_path / "CV-001-use-utc.md"

    def test_different_id(self, tmp_path: Path) -> None:
        result = convention_file_path("CV-042", "Use UTC", tmp_path)
        assert result == tmp_path / "CV-042-use-utc.md"

    def test_long_title(self, tmp_path: Path) -> None:
        result = convention_file_path("CV-001", "Future annotations import", tmp_path)
        assert result == tmp_path / "CV-001-future-annotations-import.md"


# ---------------------------------------------------------------------------
# split_scope
# ---------------------------------------------------------------------------


class TestSplitScope:
    def test_project_scope(self) -> None:
        assert split_scope("project") == ["project"]

    def test_single_path(self) -> None:
        assert split_scope("src/auth") == ["src/auth"]

    def test_single_path_with_trailing_slash(self) -> None:
        assert split_scope("src/auth/") == ["src/auth"]

    def test_multi_path(self) -> None:
        assert split_scope("src/cli/, src/services/") == ["src/cli", "src/services"]

    def test_multi_path_no_spaces(self) -> None:
        assert split_scope("src/cli/,src/services/") == ["src/cli", "src/services"]

    def test_multi_path_extra_whitespace(self) -> None:
        assert split_scope("  src/cli/ ,  src/services/  ") == ["src/cli", "src/services"]

    def test_empty_parts_filtered(self) -> None:
        assert split_scope("src/cli/,,src/services/") == ["src/cli", "src/services"]

    def test_dot_scope(self) -> None:
        assert split_scope(".") == ["."]
