"""Tests for init/rules/codex.py — Codex environment rule generation."""

from __future__ import annotations

from pathlib import Path

from lexibrary.init.rules.codex import generate_codex_rules
from lexibrary.init.rules.markers import MARKER_END, MARKER_START

# ---------------------------------------------------------------------------
# Create from scratch
# ---------------------------------------------------------------------------


class TestCreateFromScratch:
    """AGENTS.md created from scratch when file does not exist."""

    def test_creates_agents_md(self, tmp_path: Path) -> None:
        """generate_codex_rules() creates AGENTS.md at the project root."""
        generate_codex_rules(tmp_path)
        assert (tmp_path / "AGENTS.md").exists()

    def test_agents_md_has_markers(self, tmp_path: Path) -> None:
        """Created AGENTS.md contains both start and end markers."""
        generate_codex_rules(tmp_path)
        content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert MARKER_START in content
        assert MARKER_END in content

    def test_agents_md_has_core_rules(self, tmp_path: Path) -> None:
        """Created AGENTS.md contains core Lexibrary rules."""
        generate_codex_rules(tmp_path)
        content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "START_HERE.md" in content
        assert "lexi lookup" in content

    def test_agents_md_has_orient_content(self, tmp_path: Path) -> None:
        """Created AGENTS.md includes embedded orient skill content."""
        generate_codex_rules(tmp_path)
        content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "lexi status" in content

    def test_agents_md_has_search_content(self, tmp_path: Path) -> None:
        """Created AGENTS.md includes embedded search skill content."""
        generate_codex_rules(tmp_path)
        content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "lexi search" in content

    def test_returns_agents_md_path(self, tmp_path: Path) -> None:
        """Return value includes the AGENTS.md path."""
        result = generate_codex_rules(tmp_path)
        assert len(result) == 1
        assert result[0].name == "AGENTS.md"


# ---------------------------------------------------------------------------
# Append to existing AGENTS.md
# ---------------------------------------------------------------------------


class TestAppendToExisting:
    """Existing AGENTS.md without markers gets section appended."""

    def test_preserves_existing_content(self, tmp_path: Path) -> None:
        """User content before the Lexibrary section is preserved."""
        agents_md = tmp_path / "AGENTS.md"
        user_content = "# My Agent Instructions\n\nDo important things.\n"
        agents_md.write_text(user_content, encoding="utf-8")

        generate_codex_rules(tmp_path)

        content = agents_md.read_text(encoding="utf-8")
        assert "# My Agent Instructions" in content
        assert "Do important things." in content

    def test_appends_markers(self, tmp_path: Path) -> None:
        """Markers are appended to existing content."""
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# Existing content", encoding="utf-8")

        generate_codex_rules(tmp_path)

        content = agents_md.read_text(encoding="utf-8")
        assert MARKER_START in content
        assert MARKER_END in content

    def test_existing_content_before_markers(self, tmp_path: Path) -> None:
        """Existing content appears before the marker block."""
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# Existing content", encoding="utf-8")

        generate_codex_rules(tmp_path)

        content = agents_md.read_text(encoding="utf-8")
        existing_pos = content.index("# Existing content")
        marker_pos = content.index(MARKER_START)
        assert existing_pos < marker_pos


# ---------------------------------------------------------------------------
# Update existing marked section
# ---------------------------------------------------------------------------


class TestUpdateExistingSection:
    """AGENTS.md with existing markers has section replaced."""

    def test_replaces_old_section(self, tmp_path: Path) -> None:
        """Old content between markers is replaced."""
        agents_md = tmp_path / "AGENTS.md"
        old_content = (
            f"# Custom Header\n\n"
            f"{MARKER_START}\n"
            f"outdated lexibrary rules\n"
            f"{MARKER_END}\n\n"
            f"# Custom Footer"
        )
        agents_md.write_text(old_content, encoding="utf-8")

        generate_codex_rules(tmp_path)

        content = agents_md.read_text(encoding="utf-8")
        assert "outdated lexibrary rules" not in content
        assert "START_HERE.md" in content

    def test_preserves_surrounding_content(self, tmp_path: Path) -> None:
        """Content before and after the marker block is preserved."""
        agents_md = tmp_path / "AGENTS.md"
        old_content = (
            f"# Custom Header\n\n{MARKER_START}\nold stuff\n{MARKER_END}\n\n# Custom Footer"
        )
        agents_md.write_text(old_content, encoding="utf-8")

        generate_codex_rules(tmp_path)

        content = agents_md.read_text(encoding="utf-8")
        assert "# Custom Header" in content
        assert "# Custom Footer" in content

    def test_only_one_marker_pair(self, tmp_path: Path) -> None:
        """After update, there is exactly one start and one end marker."""
        agents_md = tmp_path / "AGENTS.md"
        old_content = f"{MARKER_START}\nold\n{MARKER_END}"
        agents_md.write_text(old_content, encoding="utf-8")

        generate_codex_rules(tmp_path)

        content = agents_md.read_text(encoding="utf-8")
        assert content.count(MARKER_START) == 1
        assert content.count(MARKER_END) == 1

    def test_updated_section_has_embedded_skills(self, tmp_path: Path) -> None:
        """Updated section includes orient and search skill content."""
        agents_md = tmp_path / "AGENTS.md"
        old_content = f"{MARKER_START}\nold\n{MARKER_END}"
        agents_md.write_text(old_content, encoding="utf-8")

        generate_codex_rules(tmp_path)

        content = agents_md.read_text(encoding="utf-8")
        assert "lexi status" in content
        assert "lexi search" in content
