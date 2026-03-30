"""Tests for the playbook serializer — round-trip, omission, dates, flow lists."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from lexibrary.artifacts.playbook import PlaybookFile, PlaybookFileFrontmatter
from lexibrary.playbooks.parser import parse_playbook_file
from lexibrary.playbooks.serializer import serialize_playbook_file

# -- Round-trip --------------------------------------------------------------


class TestRoundTrip:
    def test_parse_serialize_parse(self, tmp_path: Path) -> None:
        """A parsed file, serialized, then parsed again yields identical frontmatter."""
        original = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(
                title="DB Migration",
                id="PB-001",
                trigger_files=["alembic/**", "migrations/*.py"],
                tags=["database", "migration"],
                status="active",
                source="user",
                estimated_minutes=15,
                last_verified=date(2025, 6, 15),
            ),
            body="Run the migration steps.\n\n## Steps\n\n1. [ ] Apply migrations\n",
        )

        serialized = serialize_playbook_file(original)
        p = tmp_path / "round-trip.md"
        p.write_text(serialized, encoding="utf-8")

        reparsed = parse_playbook_file(p)
        assert reparsed is not None
        assert reparsed.frontmatter.title == original.frontmatter.title
        assert reparsed.frontmatter.trigger_files == original.frontmatter.trigger_files
        assert reparsed.frontmatter.tags == original.frontmatter.tags
        assert reparsed.frontmatter.status == original.frontmatter.status
        assert reparsed.frontmatter.source == original.frontmatter.source
        assert reparsed.frontmatter.estimated_minutes == original.frontmatter.estimated_minutes
        assert reparsed.frontmatter.last_verified == original.frontmatter.last_verified

    def test_round_trip_minimal(self, tmp_path: Path) -> None:
        """Minimal playbook (only required title) round-trips cleanly."""
        original = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(title="Minimal", id="PB-001"),
            body="Overview text.\n",
        )
        serialized = serialize_playbook_file(original)
        p = tmp_path / "minimal.md"
        p.write_text(serialized, encoding="utf-8")

        reparsed = parse_playbook_file(p)
        assert reparsed is not None
        assert reparsed.frontmatter.title == "Minimal"
        assert reparsed.frontmatter.estimated_minutes is None
        assert reparsed.frontmatter.superseded_by is None


# -- Optional field omission -------------------------------------------------


class TestOptionalFieldOmission:
    def test_none_fields_omitted(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(
                title="Test",
                id="PB-001",
                estimated_minutes=None,
                superseded_by=None,
                deprecated_at=None,
            ),
            body="Body.\n",
        )
        result = serialize_playbook_file(playbook)
        assert "estimated_minutes" not in result
        assert "superseded_by" not in result
        assert "deprecated_at" not in result

    def test_empty_aliases_omitted(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(title="Test", id="PB-001", aliases=[]),
            body="Body.\n",
        )
        result = serialize_playbook_file(playbook)
        assert "aliases" not in result

    def test_populated_optional_fields_present(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(
                title="Test",
                id="PB-001",
                estimated_minutes=30,
                superseded_by="new-playbook",
                aliases=["alt-name"],
            ),
            body="Body.\n",
        )
        result = serialize_playbook_file(playbook)
        assert "estimated_minutes: 30" in result
        assert "superseded_by: new-playbook" in result
        assert "aliases" in result


# -- Date format -------------------------------------------------------------


class TestDateFormat:
    def test_last_verified_iso_date(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(
                title="Test",
                id="PB-001",
                last_verified=date(2025, 6, 15),
            ),
            body="Body.\n",
        )
        result = serialize_playbook_file(playbook)
        assert "last_verified: '2025-06-15'" in result or 'last_verified: "2025-06-15"' in result

    def test_deprecated_at_iso_datetime(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(
                title="Test",
                id="PB-001",
                deprecated_at=datetime(2025, 6, 15, 12, 0, 0),
            ),
            body="Body.\n",
        )
        result = serialize_playbook_file(playbook)
        assert "deprecated_at:" in result
        assert "2025-06-15T12:00:00" in result


# -- Flow list ---------------------------------------------------------------


class TestFlowList:
    def test_trigger_files_flow_format(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(
                title="Test",
                id="PB-001",
                trigger_files=["pyproject.toml", "setup.cfg"],
            ),
            body="Body.\n",
        )
        result = serialize_playbook_file(playbook)
        assert "trigger_files: [pyproject.toml, setup.cfg]" in result

    def test_empty_trigger_files_flow(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(title="Test", id="PB-001"),
            body="Body.\n",
        )
        result = serialize_playbook_file(playbook)
        assert "trigger_files: []" in result

    def test_tags_flow_format(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(
                title="Test",
                id="PB-001",
                tags=["database", "migration"],
            ),
            body="Body.\n",
        )
        result = serialize_playbook_file(playbook)
        assert "tags: [database, migration]" in result


# -- YAML comment preservation -----------------------------------------------


class TestYamlComment:
    def test_title_comment_present(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(title="Test", id="PB-001"),
            body="Body.\n",
        )
        result = serialize_playbook_file(playbook)
        assert "# title: use a semantic name" in result

    def test_comment_above_title(self) -> None:
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(title="Test", id="PB-001"),
            body="Body.\n",
        )
        result = serialize_playbook_file(playbook)
        lines = result.splitlines()
        # Find the comment and title lines
        comment_idx = None
        title_idx = None
        for i, line in enumerate(lines):
            if line.startswith("# title: use a semantic name"):
                comment_idx = i
            if line.startswith("title: "):
                title_idx = i
        assert comment_idx is not None, "Comment not found"
        assert title_idx is not None, "Title line not found"
        assert title_idx == comment_idx + 1, "Title should be immediately after comment"

    def test_comment_preserved_through_round_trip(self, tmp_path: Path) -> None:
        """Serialized output includes the tooltip comment; re-parsing still works."""
        playbook = PlaybookFile(
            frontmatter=PlaybookFileFrontmatter(title="Release Checklist", id="PB-001"),
            body="Follow these steps.\n",
        )
        serialized = serialize_playbook_file(playbook)
        assert "# title: use a semantic name" in serialized

        p = tmp_path / "release.md"
        p.write_text(serialized, encoding="utf-8")
        reparsed = parse_playbook_file(p)
        assert reparsed is not None
        assert reparsed.frontmatter.title == "Release Checklist"
