"""Tests for init/rules/claude.py — Claude Code environment rule generation."""

from __future__ import annotations

from pathlib import Path

from lexibrary.init.rules.claude import generate_claude_rules
from lexibrary.init.rules.markers import MARKER_END, MARKER_START

# ---------------------------------------------------------------------------
# Create from scratch
# ---------------------------------------------------------------------------


class TestCreateFromScratch:
    """CLAUDE.md created from scratch when file does not exist."""

    def test_creates_claude_md(self, tmp_path: Path) -> None:
        """generate_claude_rules() creates CLAUDE.md at the project root."""
        generate_claude_rules(tmp_path)
        assert (tmp_path / "CLAUDE.md").exists()

    def test_claude_md_has_markers(self, tmp_path: Path) -> None:
        """Created CLAUDE.md contains both start and end markers."""
        generate_claude_rules(tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert MARKER_START in content
        assert MARKER_END in content

    def test_claude_md_has_core_rules(self, tmp_path: Path) -> None:
        """Created CLAUDE.md contains core Lexibrary rules."""
        generate_claude_rules(tmp_path)
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "START_HERE.md" in content
        assert "lexi lookup" in content

    def test_returns_all_created_paths(self, tmp_path: Path) -> None:
        """Return value includes CLAUDE.md and both command files."""
        result = generate_claude_rules(tmp_path)
        assert len(result) == 3
        filenames = [p.name for p in result]
        assert "CLAUDE.md" in filenames
        assert "lexi-orient.md" in filenames
        assert "lexi-search.md" in filenames


# ---------------------------------------------------------------------------
# Append to existing CLAUDE.md without markers
# ---------------------------------------------------------------------------


class TestAppendToExisting:
    """Existing CLAUDE.md without markers gets section appended."""

    def test_preserves_existing_content(self, tmp_path: Path) -> None:
        """User content before the Lexibrary section is preserved."""
        claude_md = tmp_path / "CLAUDE.md"
        user_content = "# My Project\n\nCustom rules here.\n"
        claude_md.write_text(user_content, encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        assert "# My Project" in content
        assert "Custom rules here." in content

    def test_appends_markers(self, tmp_path: Path) -> None:
        """Markers are appended to existing content."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Existing content", encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        assert MARKER_START in content
        assert MARKER_END in content

    def test_existing_content_before_markers(self, tmp_path: Path) -> None:
        """Existing content appears before the marker block."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Existing content", encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        existing_pos = content.index("# Existing content")
        marker_pos = content.index(MARKER_START)
        assert existing_pos < marker_pos


# ---------------------------------------------------------------------------
# Update existing marked section
# ---------------------------------------------------------------------------


class TestUpdateExistingSection:
    """CLAUDE.md with existing markers has section replaced."""

    def test_replaces_old_section(self, tmp_path: Path) -> None:
        """Old content between markers is replaced."""
        claude_md = tmp_path / "CLAUDE.md"
        old_content = (
            f"# My Rules\n\n{MARKER_START}\nold lexibrary rules\n{MARKER_END}\n\n# My Other Rules"
        )
        claude_md.write_text(old_content, encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        assert "old lexibrary rules" not in content
        assert "START_HERE.md" in content

    def test_preserves_surrounding_content(self, tmp_path: Path) -> None:
        """Content before and after the marker block is preserved."""
        claude_md = tmp_path / "CLAUDE.md"
        old_content = (
            f"# Before Section\n\n{MARKER_START}\nold stuff\n{MARKER_END}\n\n# After Section"
        )
        claude_md.write_text(old_content, encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        assert "# Before Section" in content
        assert "# After Section" in content

    def test_only_one_marker_pair(self, tmp_path: Path) -> None:
        """After update, there is exactly one start and one end marker."""
        claude_md = tmp_path / "CLAUDE.md"
        old_content = f"{MARKER_START}\nold\n{MARKER_END}"
        claude_md.write_text(old_content, encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = claude_md.read_text(encoding="utf-8")
        assert content.count(MARKER_START) == 1
        assert content.count(MARKER_END) == 1


# ---------------------------------------------------------------------------
# Command files
# ---------------------------------------------------------------------------


class TestCommandFiles:
    """Command files are created in .claude/commands/."""

    def test_creates_orient_command(self, tmp_path: Path) -> None:
        """lexi-orient.md is created in .claude/commands/."""
        generate_claude_rules(tmp_path)
        orient = tmp_path / ".claude" / "commands" / "lexi-orient.md"
        assert orient.exists()

    def test_orient_contains_start_here(self, tmp_path: Path) -> None:
        """Orient command references START_HERE.md."""
        generate_claude_rules(tmp_path)
        orient = tmp_path / ".claude" / "commands" / "lexi-orient.md"
        content = orient.read_text(encoding="utf-8")
        assert "START_HERE.md" in content

    def test_orient_contains_lexi_status(self, tmp_path: Path) -> None:
        """Orient command includes lexi status."""
        generate_claude_rules(tmp_path)
        orient = tmp_path / ".claude" / "commands" / "lexi-orient.md"
        content = orient.read_text(encoding="utf-8")
        assert "lexi status" in content

    def test_creates_search_command(self, tmp_path: Path) -> None:
        """lexi-search.md is created in .claude/commands/."""
        generate_claude_rules(tmp_path)
        search = tmp_path / ".claude" / "commands" / "lexi-search.md"
        assert search.exists()

    def test_search_contains_lexi_search(self, tmp_path: Path) -> None:
        """Search command references lexi search."""
        generate_claude_rules(tmp_path)
        search = tmp_path / ".claude" / "commands" / "lexi-search.md"
        content = search.read_text(encoding="utf-8")
        assert "lexi search" in content

    def test_command_files_overwritten_on_update(self, tmp_path: Path) -> None:
        """Command files are overwritten when regenerated."""
        orient = tmp_path / ".claude" / "commands" / "lexi-orient.md"
        orient.parent.mkdir(parents=True, exist_ok=True)
        orient.write_text("old orient content", encoding="utf-8")

        generate_claude_rules(tmp_path)

        content = orient.read_text(encoding="utf-8")
        assert "old orient content" not in content
        assert "START_HERE.md" in content

    def test_creates_commands_directory(self, tmp_path: Path) -> None:
        """The .claude/commands/ directory is created if it does not exist."""
        generate_claude_rules(tmp_path)
        assert (tmp_path / ".claude" / "commands").is_dir()
