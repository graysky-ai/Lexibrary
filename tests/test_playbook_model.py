"""Tests for the playbook artifact model, slug helpers, and re-exports."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from lexibrary.artifacts import (
    PlaybookFile,
    PlaybookFileFrontmatter,
    playbook_file_path,
    playbook_slug,
)

# -- PlaybookFileFrontmatter defaults ----------------------------------------


class TestPlaybookFileFrontmatterDefaults:
    def test_default_field_values(self) -> None:
        fm = PlaybookFileFrontmatter(title="Test")
        assert fm.title == "Test"
        assert fm.trigger_files == []
        assert fm.tags == []
        assert fm.status == "draft"
        assert fm.source == "user"
        assert fm.estimated_minutes is None
        assert fm.last_verified is None
        assert fm.deprecated_at is None
        assert fm.superseded_by is None
        assert fm.aliases == []

    def test_title_is_required(self) -> None:
        with pytest.raises(ValidationError):
            PlaybookFileFrontmatter()  # type: ignore[call-arg]


# -- PlaybookFileFrontmatter validation --------------------------------------


class TestPlaybookFileFrontmatterValidation:
    def test_invalid_status_raises(self) -> None:
        with pytest.raises(ValidationError):
            PlaybookFileFrontmatter(title="Test", status="archived")  # type: ignore[arg-type]

    def test_valid_statuses(self) -> None:
        for status in ("draft", "active", "deprecated"):
            fm = PlaybookFileFrontmatter(title="Test", status=status)  # type: ignore[arg-type]
            assert fm.status == status

    def test_invalid_source_raises(self) -> None:
        with pytest.raises(ValidationError):
            PlaybookFileFrontmatter(title="Test", source="config")  # type: ignore[arg-type]

    def test_all_fields_populated(self) -> None:
        now = datetime(2025, 6, 15, 12, 0, 0)
        today = date(2025, 6, 15)
        fm = PlaybookFileFrontmatter(
            title="DB Migration",
            trigger_files=["alembic/**"],
            tags=["database", "migration"],
            status="active",
            source="agent",
            estimated_minutes=10,
            last_verified=today,
            deprecated_at=now,
            superseded_by="db-migration-v2",
            aliases=["migration"],
        )
        assert fm.trigger_files == ["alembic/**"]
        assert fm.tags == ["database", "migration"]
        assert fm.estimated_minutes == 10
        assert fm.last_verified == today
        assert fm.deprecated_at == now
        assert fm.superseded_by == "db-migration-v2"
        assert fm.aliases == ["migration"]


# -- PlaybookFile ------------------------------------------------------------


class TestPlaybookFile:
    def test_name_property(self) -> None:
        pb = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(title="Version Bump"),
        )
        assert pb.name == "Version Bump"

    def test_defaults(self) -> None:
        pb = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(title="Test"),
        )
        assert pb.body == ""
        assert pb.overview == ""
        assert pb.file_path is None

    def test_with_body_and_overview(self) -> None:
        pb = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(title="Test"),
            body="# Steps\n\n- [ ] Step 1",
            overview="This playbook covers step 1.",
            file_path=Path("/tmp/playbooks/test.md"),
        )
        assert pb.body == "# Steps\n\n- [ ] Step 1"
        assert pb.overview == "This playbook covers step 1."
        assert pb.file_path == Path("/tmp/playbooks/test.md")


# -- Title field description --------------------------------------------------


class TestTitleFieldDescription:
    def test_title_has_field_description(self) -> None:
        field_info = PlaybookFileFrontmatter.model_fields["title"]
        assert field_info.description is not None
        assert "canonical identifier" in field_info.description.lower()


# -- Slug helpers ------------------------------------------------------------


class TestPlaybookSlug:
    def test_basic_slug(self) -> None:
        assert playbook_slug("DB Migration") == "db-migration"

    def test_slug_with_special_characters(self) -> None:
        assert playbook_slug("Version Bump (Major)") == "version-bump-major"

    def test_slug_strips_leading_trailing(self) -> None:
        assert playbook_slug("  Hello World  ") == "hello-world"


class TestPlaybookFilePath:
    def test_basic_file_path(self) -> None:
        result = playbook_file_path("Version Bump", Path("/p/playbooks"))
        assert result == Path("/p/playbooks/version-bump.md")

    def test_collision_append(self, tmp_path: Path) -> None:
        playbooks_dir = tmp_path / "playbooks"
        playbooks_dir.mkdir()
        # Create the first file to cause a collision
        (playbooks_dir / "version-bump.md").touch()

        result = playbook_file_path("Version Bump", playbooks_dir)
        assert result == playbooks_dir / "version-bump-2.md"

    def test_multiple_collisions(self, tmp_path: Path) -> None:
        playbooks_dir = tmp_path / "playbooks"
        playbooks_dir.mkdir()
        (playbooks_dir / "test.md").touch()
        (playbooks_dir / "test-2.md").touch()

        result = playbook_file_path("Test", playbooks_dir)
        assert result == playbooks_dir / "test-3.md"
