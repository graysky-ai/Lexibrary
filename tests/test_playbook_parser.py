"""Tests for the playbook parser — valid files, missing frontmatter, invalid YAML, YAML comments."""

from __future__ import annotations

from pathlib import Path

from lexibrary.playbooks.parser import (
    _FRONTMATTER_RE,
    extract_overview,
    parse_playbook_file,
)

# -- extract_overview --------------------------------------------------------


class TestExtractOverview:
    def test_first_paragraph(self) -> None:
        body = "This is the overview.\n\nSecond paragraph here."
        assert extract_overview(body) == "This is the overview."

    def test_multiline_first_paragraph(self) -> None:
        body = "Line one\nline two\n\nSecond paragraph."
        assert extract_overview(body) == "Line one\nline two"

    def test_empty_body(self) -> None:
        assert extract_overview("") == ""

    def test_whitespace_only(self) -> None:
        assert extract_overview("   \n\n  ") == ""

    def test_single_paragraph(self) -> None:
        body = "Only one paragraph."
        assert extract_overview(body) == "Only one paragraph."

    def test_leading_whitespace_stripped(self) -> None:
        body = "\n\n  First paragraph.\n\nSecond."
        assert extract_overview(body) == "First paragraph."


# -- _FRONTMATTER_RE --------------------------------------------------------


class TestFrontmatterRegex:
    def test_matches_valid_frontmatter(self) -> None:
        text = "---\ntitle: Test\nid: CN-001\n---\nBody here."
        m = _FRONTMATTER_RE.match(text)
        assert m is not None
        assert "title: Test" in m.group(1)

    def test_no_match_without_delimiters(self) -> None:
        text = "No frontmatter here."
        assert _FRONTMATTER_RE.match(text) is None

    def test_matches_frontmatter_with_yaml_comment(self) -> None:
        text = "---\n# title: use a semantic name\ntitle: My Playbook\n---\nBody."
        m = _FRONTMATTER_RE.match(text)
        assert m is not None
        assert "title: My Playbook" in m.group(1)


# -- parse_playbook_file ----------------------------------------------------


class TestParsePlaybookFile:
    def test_valid_file(self, tmp_path: Path) -> None:
        content = (
            "---\n"
            "title: DB Migration\n"
            "id: PB-001\n"
            "trigger_files: [alembic/**]\n"
            "tags: [database]\n"
            "status: active\n"
            "source: user\n"
            "---\n"
            "This is the overview.\n"
            "\n"
            "## Steps\n"
            "\n"
            "1. [ ] Run migrations\n"
        )
        p = tmp_path / "db-migration.md"
        p.write_text(content, encoding="utf-8")

        result = parse_playbook_file(p)
        assert result is not None
        assert result.frontmatter.title == "DB Migration"
        assert result.frontmatter.trigger_files == ["alembic/**"]
        assert result.frontmatter.tags == ["database"]
        assert result.frontmatter.status == "active"
        assert result.overview == "This is the overview."
        assert result.file_path == p

    def test_missing_file(self, tmp_path: Path) -> None:
        result = parse_playbook_file(tmp_path / "nonexistent.md")
        assert result is None

    def test_missing_frontmatter(self, tmp_path: Path) -> None:
        p = tmp_path / "no-fm.md"
        p.write_text("Just some text, no frontmatter.", encoding="utf-8")
        result = parse_playbook_file(p)
        assert result is None

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        content = "---\ntitle: [unclosed bracket\nid: CN-002\n---\nBody.\n"
        p = tmp_path / "bad-yaml.md"
        p.write_text(content, encoding="utf-8")
        result = parse_playbook_file(p)
        assert result is None

    def test_yaml_not_a_dict(self, tmp_path: Path) -> None:
        content = "---\n- just a list\n---\nBody.\n"
        p = tmp_path / "list-yaml.md"
        p.write_text(content, encoding="utf-8")
        result = parse_playbook_file(p)
        assert result is None

    def test_invalid_frontmatter_values(self, tmp_path: Path) -> None:
        # Missing required title field
        content = "---\nstatus: active\n---\nBody.\n"
        p = tmp_path / "no-title.md"
        p.write_text(content, encoding="utf-8")
        result = parse_playbook_file(p)
        assert result is None

    def test_yaml_comment_handling(self, tmp_path: Path) -> None:
        content = (
            "---\n"
            "# title: use a semantic name that describes the procedure\n"
            "title: Release Checklist\n"
            "id: PB-002\n"
            "trigger_files: []\n"
            "tags: [release]\n"
            "status: draft\n"
            "source: user\n"
            "---\n"
            "Overview of release process.\n"
        )
        p = tmp_path / "release.md"
        p.write_text(content, encoding="utf-8")

        result = parse_playbook_file(p)
        assert result is not None
        assert result.frontmatter.title == "Release Checklist"
        assert result.overview == "Overview of release process."

    def test_empty_body(self, tmp_path: Path) -> None:
        content = "---\ntitle: Minimal\nid: CN-003\n---\n"
        p = tmp_path / "minimal.md"
        p.write_text(content, encoding="utf-8")

        result = parse_playbook_file(p)
        assert result is not None
        assert result.body == ""
        assert result.overview == ""

    def test_defaults_applied(self, tmp_path: Path) -> None:
        content = "---\ntitle: Defaults Test\nid: CN-004\n---\nBody.\n"
        p = tmp_path / "defaults.md"
        p.write_text(content, encoding="utf-8")

        result = parse_playbook_file(p)
        assert result is not None
        assert result.frontmatter.trigger_files == []
        assert result.frontmatter.tags == []
        assert result.frontmatter.status == "draft"
        assert result.frontmatter.source == "user"
        assert result.frontmatter.estimated_minutes is None
