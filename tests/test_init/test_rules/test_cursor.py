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
        assert "lexi orient" in content
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
        assert "lexi orient" in content
        assert "topology" in content.lower()

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

    def test_returns_three_paths(self, tmp_path: Path) -> None:
        """Return value includes MDC, editing MDC, and skills file paths."""
        result = generate_cursor_rules(tmp_path)
        assert len(result) == 3

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

    def test_returns_editing_mdc_path(self, tmp_path: Path) -> None:
        """Return value includes the editing MDC file path."""
        result = generate_cursor_rules(tmp_path)
        filenames = [p.name for p in result]
        assert "lexibrary-editing.mdc" in filenames


# ---------------------------------------------------------------------------
# Editing MDC rules file
# ---------------------------------------------------------------------------


class TestEditingMDCRulesFile:
    """Cursor editing-scoped MDC rules file generation."""

    def test_creates_editing_mdc_file(self, tmp_path: Path) -> None:
        """generate_cursor_rules() creates .cursor/rules/lexibrary-editing.mdc."""
        generate_cursor_rules(tmp_path)
        editing_mdc = tmp_path / ".cursor" / "rules" / "lexibrary-editing.mdc"
        assert editing_mdc.exists()

    def test_editing_mdc_has_yaml_frontmatter(self, tmp_path: Path) -> None:
        """Editing MDC file starts with YAML frontmatter delimiters."""
        generate_cursor_rules(tmp_path)
        editing_mdc = tmp_path / ".cursor" / "rules" / "lexibrary-editing.mdc"
        content = editing_mdc.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "\n---\n" in content

    def test_editing_mdc_has_always_apply_false(self, tmp_path: Path) -> None:
        """Editing MDC frontmatter includes alwaysApply: false."""
        generate_cursor_rules(tmp_path)
        editing_mdc = tmp_path / ".cursor" / "rules" / "lexibrary-editing.mdc"
        content = editing_mdc.read_text(encoding="utf-8")
        assert "alwaysApply: false" in content

    def test_editing_mdc_has_description(self, tmp_path: Path) -> None:
        """Editing MDC frontmatter includes a description field."""
        generate_cursor_rules(tmp_path)
        editing_mdc = tmp_path / ".cursor" / "rules" / "lexibrary-editing.mdc"
        content = editing_mdc.read_text(encoding="utf-8")
        assert "description:" in content

    def test_editing_mdc_has_default_glob(self, tmp_path: Path) -> None:
        """Editing MDC uses default scope_root glob pattern."""
        generate_cursor_rules(tmp_path)
        editing_mdc = tmp_path / ".cursor" / "rules" / "lexibrary-editing.mdc"
        content = editing_mdc.read_text(encoding="utf-8")
        assert "src/**" in content

    def test_editing_mdc_custom_scope_root(self, tmp_path: Path) -> None:
        """Editing MDC uses custom scope_root for glob pattern."""
        generate_cursor_rules(tmp_path, scope_root="lib")
        editing_mdc = tmp_path / ".cursor" / "rules" / "lexibrary-editing.mdc"
        content = editing_mdc.read_text(encoding="utf-8")
        assert "lib/**" in content

    def test_editing_mdc_mentions_lexi_lookup(self, tmp_path: Path) -> None:
        """Editing MDC body references lexi lookup."""
        generate_cursor_rules(tmp_path)
        editing_mdc = tmp_path / ".cursor" / "rules" / "lexibrary-editing.mdc"
        content = editing_mdc.read_text(encoding="utf-8")
        assert "lexi lookup" in content

    def test_editing_mdc_mentions_design_files(self, tmp_path: Path) -> None:
        """Editing MDC body mentions updating design files."""
        generate_cursor_rules(tmp_path)
        editing_mdc = tmp_path / ".cursor" / "rules" / "lexibrary-editing.mdc"
        content = editing_mdc.read_text(encoding="utf-8")
        assert "design file" in content.lower()

    def test_editing_mdc_overwritten_on_update(self, tmp_path: Path) -> None:
        """Editing MDC file is overwritten when regenerated."""
        editing_mdc = tmp_path / ".cursor" / "rules" / "lexibrary-editing.mdc"
        editing_mdc.parent.mkdir(parents=True, exist_ok=True)
        editing_mdc.write_text("old editing rules", encoding="utf-8")

        generate_cursor_rules(tmp_path)

        content = editing_mdc.read_text(encoding="utf-8")
        assert "old editing rules" not in content
        assert "alwaysApply: false" in content


# ---------------------------------------------------------------------------
# Skills file — new skills
# ---------------------------------------------------------------------------


class TestSkillsFileNewSkills:
    """Skills file includes new lookup, concepts, and stack skills."""

    def test_skills_has_lookup_content(self, tmp_path: Path) -> None:
        """Skills file contains lookup skill content."""
        generate_cursor_rules(tmp_path)
        skills = tmp_path / ".cursor" / "skills" / "lexi.md"
        content = skills.read_text(encoding="utf-8")
        assert "lexi lookup" in content

    def test_skills_has_concepts_content(self, tmp_path: Path) -> None:
        """Skills file contains concepts skill content."""
        generate_cursor_rules(tmp_path)
        skills = tmp_path / ".cursor" / "skills" / "lexi.md"
        content = skills.read_text(encoding="utf-8")
        assert "lexi concept" in content

    def test_skills_has_stack_content(self, tmp_path: Path) -> None:
        """Skills file contains stack skill content."""
        generate_cursor_rules(tmp_path)
        skills = tmp_path / ".cursor" / "skills" / "lexi.md"
        content = skills.read_text(encoding="utf-8")
        assert "lexi stack" in content
