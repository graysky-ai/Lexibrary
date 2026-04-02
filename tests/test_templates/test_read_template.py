"""Tests for the lexibrary.templates package and read_template() helper."""

from __future__ import annotations

import pytest

from lexibrary.templates import read_template

# ---------------------------------------------------------------------------
# The complete manifest of template files that must ship with the package.
# TG2–TG6 will populate these with real content; for now they are placeholders.
# ---------------------------------------------------------------------------
EXPECTED_TEMPLATES: list[str] = [
    "config/default_config.yaml",
    "rules/core_rules.md",
    "rules/skills/lexi-search/SKILL.md",
    "rules/skills/lexi-lookup/SKILL.md",
    "rules/skills/lexi-concept/SKILL.md",
    "rules/skills/lexi-stack/SKILL.md",
    "claude/agents/explore.md",
    "claude/agents/plan.md",
    "claude/agents/code.md",
    "claude/agents/lexi-research.md",
    "claude/hooks/lexi-pre-edit.sh",
    "claude/hooks/lexi-post-edit.sh",
    "cursor/editing-rules.md",
    "hooks/pre-commit.sh",
    "hooks/post-commit.sh",
    "lifecycle/queue_header.txt",
    "scaffolder/lexignore_header.txt",
    "scaffolder/config_yaml_header.txt",
]


class TestReadTemplate:
    """Tests for read_template()."""

    def test_loads_known_template(self) -> None:
        """read_template() returns non-empty content for a known template."""
        content = read_template("rules/core_rules.md")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_preserves_content_verbatim(self) -> None:
        """read_template() returns content verbatim."""
        content = read_template("rules/core_rules.md")
        # The template content ends with the last line of text
        assert content.endswith("work.") or content.endswith("\n")

    def test_raises_on_missing_template(self) -> None:
        """read_template() raises FileNotFoundError for nonexistent paths."""
        with pytest.raises(FileNotFoundError, match="Template not found"):
            read_template("nonexistent/file.md")

    def test_raises_on_empty_path(self) -> None:
        """read_template() raises on an empty resource path."""
        with pytest.raises((FileNotFoundError, ValueError)):
            read_template("")


class TestTemplateManifest:
    """Ensure all expected template files exist and are loadable.

    This acts as a guard against accidental deletion of template files.
    """

    @pytest.mark.parametrize("path", EXPECTED_TEMPLATES)
    def test_template_exists(self, path: str) -> None:
        """Each expected template file must be loadable via read_template()."""
        content = read_template(path)
        assert isinstance(content, str)
        assert len(content) > 0, f"Template {path} is empty"
