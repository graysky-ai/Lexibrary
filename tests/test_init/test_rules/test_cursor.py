"""Tests for init/rules/cursor.py — Cursor environment rule generation."""

from __future__ import annotations

from pathlib import Path

from lexibrary.init.rules.cursor import generate_cursor_rules

# ---------------------------------------------------------------------------
# MDC rules file
# ---------------------------------------------------------------------------


class TestMDCRulesFile:
    """Cursor MDC rules file generation."""

    def test_creates_mdc_file(self, tmp_path: Path) -> None:
        """generate_cursor_rules() creates .cursor/rules/lexibrary.mdc."""
        generate_cursor_rules(tmp_path)
        mdc = tmp_path / ".cursor" / "rules" / "lexibrary.mdc"
        assert mdc.exists()

    def test_mdc_has_yaml_frontmatter(self, tmp_path: Path) -> None:
        """MDC file starts with YAML frontmatter delimiters."""
        generate_cursor_rules(tmp_path)
        mdc = tmp_path / ".cursor" / "rules" / "lexibrary.mdc"
        content = mdc.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        # Should have closing frontmatter delimiter
        assert "\n---\n" in content

    def test_mdc_has_always_apply(self, tmp_path: Path) -> None:
        """MDC frontmatter includes alwaysApply: true."""
        generate_cursor_rules(tmp_path)
        mdc = tmp_path / ".cursor" / "rules" / "lexibrary.mdc"
        content = mdc.read_text(encoding="utf-8")
        assert "alwaysApply: true" in content

    def test_mdc_has_description(self, tmp_path: Path) -> None:
        """MDC frontmatter includes a description field."""
        generate_cursor_rules(tmp_path)
        mdc = tmp_path / ".cursor" / "rules" / "lexibrary.mdc"
        content = mdc.read_text(encoding="utf-8")
        assert "description:" in content

    def test_mdc_has_globs(self, tmp_path: Path) -> None:
        """MDC frontmatter includes a globs field."""
        generate_cursor_rules(tmp_path)
        mdc = tmp_path / ".cursor" / "rules" / "lexibrary.mdc"
        content = mdc.read_text(encoding="utf-8")
        assert "globs:" in content

    def test_mdc_has_core_rules(self, tmp_path: Path) -> None:
        """MDC file body contains core Lexibrary rules."""
        generate_cursor_rules(tmp_path)
        mdc = tmp_path / ".cursor" / "rules" / "lexibrary.mdc"
        content = mdc.read_text(encoding="utf-8")
        assert "START_HERE.md" in content
        assert "lexi lookup" in content

    def test_mdc_overwritten_on_update(self, tmp_path: Path) -> None:
        """MDC file is overwritten when regenerated."""
        mdc = tmp_path / ".cursor" / "rules" / "lexibrary.mdc"
        mdc.parent.mkdir(parents=True, exist_ok=True)
        mdc.write_text("old cursor rules", encoding="utf-8")

        generate_cursor_rules(tmp_path)

        content = mdc.read_text(encoding="utf-8")
        assert "old cursor rules" not in content
        assert "alwaysApply: true" in content

    def test_creates_rules_directory(self, tmp_path: Path) -> None:
        """.cursor/rules/ directory is created if it does not exist."""
        generate_cursor_rules(tmp_path)
        assert (tmp_path / ".cursor" / "rules").is_dir()


# ---------------------------------------------------------------------------
# Skills file
# ---------------------------------------------------------------------------


class TestSkillsFile:
    """Cursor combined skills file generation."""

    def test_creates_skills_file(self, tmp_path: Path) -> None:
        """generate_cursor_rules() creates .cursor/skills/lexi.md."""
        generate_cursor_rules(tmp_path)
        skills = tmp_path / ".cursor" / "skills" / "lexi.md"
        assert skills.exists()

    def test_skills_has_orient_content(self, tmp_path: Path) -> None:
        """Skills file contains orient skill content."""
        generate_cursor_rules(tmp_path)
        skills = tmp_path / ".cursor" / "skills" / "lexi.md"
        content = skills.read_text(encoding="utf-8")
        assert "START_HERE.md" in content
        assert "lexi status" in content

    def test_skills_has_search_content(self, tmp_path: Path) -> None:
        """Skills file contains search skill content."""
        generate_cursor_rules(tmp_path)
        skills = tmp_path / ".cursor" / "skills" / "lexi.md"
        content = skills.read_text(encoding="utf-8")
        assert "lexi search" in content

    def test_skills_overwritten_on_update(self, tmp_path: Path) -> None:
        """Skills file is overwritten when regenerated."""
        skills = tmp_path / ".cursor" / "skills" / "lexi.md"
        skills.parent.mkdir(parents=True, exist_ok=True)
        skills.write_text("old skills content", encoding="utf-8")

        generate_cursor_rules(tmp_path)

        content = skills.read_text(encoding="utf-8")
        assert "old skills content" not in content

    def test_creates_skills_directory(self, tmp_path: Path) -> None:
        """.cursor/skills/ directory is created if it does not exist."""
        generate_cursor_rules(tmp_path)
        assert (tmp_path / ".cursor" / "skills").is_dir()


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------


class TestReturnValue:
    """generate_cursor_rules() returns correct paths."""

    def test_returns_two_paths(self, tmp_path: Path) -> None:
        """Return value includes both MDC and skills file paths."""
        result = generate_cursor_rules(tmp_path)
        assert len(result) == 2

    def test_returns_mdc_path(self, tmp_path: Path) -> None:
        """Return value includes the MDC file path."""
        result = generate_cursor_rules(tmp_path)
        filenames = [p.name for p in result]
        assert "lexibrary.mdc" in filenames

    def test_returns_skills_path(self, tmp_path: Path) -> None:
        """Return value includes the skills file path."""
        result = generate_cursor_rules(tmp_path)
        filenames = [p.name for p in result]
        assert "lexi.md" in filenames
