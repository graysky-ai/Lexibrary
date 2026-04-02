"""Tests for init/rules/generic.py -- Generic environment rule generation."""

from __future__ import annotations

from pathlib import Path

from lexibrary.init.rules import generate_rules, supported_environments
from lexibrary.init.rules.generic import generate_generic_rules

# ---------------------------------------------------------------------------
# Create from scratch
# ---------------------------------------------------------------------------


class TestCreateFromScratch:
    """LEXIBRARY_RULES.md created from scratch when file does not exist."""

    def test_creates_rules_md(self, tmp_path: Path) -> None:
        """generate_generic_rules() creates LEXIBRARY_RULES.md at the project root."""
        generate_generic_rules(tmp_path)
        assert (tmp_path / "LEXIBRARY_RULES.md").exists()

    def test_rules_md_has_core_rules(self, tmp_path: Path) -> None:
        """Created LEXIBRARY_RULES.md contains core Lexibrary rules."""
        generate_generic_rules(tmp_path)
        content = (tmp_path / "LEXIBRARY_RULES.md").read_text(encoding="utf-8")
        assert "TOPOLOGY.md" in content
        assert "lexi lookup" in content

    def test_rules_md_has_topology_reference(self, tmp_path: Path) -> None:
        """Created LEXIBRARY_RULES.md references TOPOLOGY.md for session start."""
        generate_generic_rules(tmp_path)
        content = (tmp_path / "LEXIBRARY_RULES.md").read_text(encoding="utf-8")
        assert "TOPOLOGY.md" in content

    def test_rules_md_has_search_content(self, tmp_path: Path) -> None:
        """Created LEXIBRARY_RULES.md includes embedded search skill content."""
        generate_generic_rules(tmp_path)
        content = (tmp_path / "LEXIBRARY_RULES.md").read_text(encoding="utf-8")
        assert "lexi search" in content

    def test_returns_rules_md_path(self, tmp_path: Path) -> None:
        """Return value includes the LEXIBRARY_RULES.md path."""
        result = generate_generic_rules(tmp_path)
        assert len(result) == 1
        assert result[0].name == "LEXIBRARY_RULES.md"

    def test_returned_path_is_absolute(self, tmp_path: Path) -> None:
        """Returned path is an absolute path."""
        result = generate_generic_rules(tmp_path)
        assert result[0].is_absolute()

    def test_returned_path_matches_project_root(self, tmp_path: Path) -> None:
        """Returned path is under the project root."""
        result = generate_generic_rules(tmp_path)
        assert result[0].parent == tmp_path


# ---------------------------------------------------------------------------
# Overwrite on regeneration
# ---------------------------------------------------------------------------


class TestOverwriteOnRegeneration:
    """Existing LEXIBRARY_RULES.md is fully overwritten on regeneration."""

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Old content is replaced when regenerating."""
        rules_md = tmp_path / "LEXIBRARY_RULES.md"
        rules_md.write_text("old content that should be replaced", encoding="utf-8")

        generate_generic_rules(tmp_path)

        content = rules_md.read_text(encoding="utf-8")
        assert "old content that should be replaced" not in content
        assert "TOPOLOGY.md" in content

    def test_idempotent_content(self, tmp_path: Path) -> None:
        """Running twice produces identical content."""
        generate_generic_rules(tmp_path)
        first = (tmp_path / "LEXIBRARY_RULES.md").read_text(encoding="utf-8")

        generate_generic_rules(tmp_path)
        second = (tmp_path / "LEXIBRARY_RULES.md").read_text(encoding="utf-8")

        assert first == second


# ---------------------------------------------------------------------------
# Registration in __init__.py
# ---------------------------------------------------------------------------


class TestRegistration:
    """Generic environment is registered in the rules package."""

    def test_supported_environments_includes_generic(self) -> None:
        """supported_environments() includes 'generic'."""
        envs = supported_environments()
        assert "generic" in envs

    def test_generate_rules_with_generic(self, tmp_path: Path) -> None:
        """generate_rules() works with 'generic' environment."""
        result = generate_rules(tmp_path, ["generic"])
        assert "generic" in result
        assert len(result["generic"]) == 1
        assert result["generic"][0].name == "LEXIBRARY_RULES.md"

    def test_generate_rules_generic_creates_file(self, tmp_path: Path) -> None:
        """generate_rules() with 'generic' creates the LEXIBRARY_RULES.md file."""
        generate_rules(tmp_path, ["generic"])
        assert (tmp_path / "LEXIBRARY_RULES.md").exists()
