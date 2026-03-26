"""Tests that .claude/skills/ mirrors src/lexibrary/templates/rules/skills/.

The source templates under src/lexibrary/templates/rules/skills/ are the
canonical copies of all skill files.  The .claude/skills/ directory is a
dogfood mirror that Claude Code reads at runtime.  This test ensures every
file in the source tree has an identical copy in the mirror, catching drift
before it reaches users.

Design decision 6 from topology-builder-improvements specifies that the test
covers ALL skill templates, not just topology-builder, so any new skill
template automatically gets coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _project_root() -> Path:
    """Walk up from this test file to the directory containing pyproject.toml."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    msg = "Could not find project root (no pyproject.toml found)"
    raise RuntimeError(msg)


ROOT = _project_root()
SOURCE_SKILLS_DIR = ROOT / "src" / "lexibrary" / "templates" / "rules" / "skills"
MIRROR_SKILLS_DIR = ROOT / ".claude" / "skills"


def _collect_source_skill_files() -> list[str]:
    """Return relative paths of all files under the source skills directory."""
    if not SOURCE_SKILLS_DIR.is_dir():
        return []
    return sorted(
        str(p.relative_to(SOURCE_SKILLS_DIR))
        for p in SOURCE_SKILLS_DIR.rglob("*")
        if p.is_file()
    )


SOURCE_SKILL_FILES = _collect_source_skill_files()


class TestSkillsMirror:
    """Assert every source skill file has an identical copy in .claude/skills/."""

    def test_source_skills_directory_exists(self) -> None:
        """The source skills directory must exist."""
        assert SOURCE_SKILLS_DIR.is_dir(), (
            f"Source skills directory not found: {SOURCE_SKILLS_DIR}"
        )

    def test_mirror_skills_directory_exists(self) -> None:
        """The mirror skills directory must exist."""
        assert MIRROR_SKILLS_DIR.is_dir(), (
            f"Mirror skills directory not found: {MIRROR_SKILLS_DIR}"
        )

    def test_at_least_one_source_skill_file(self) -> None:
        """There must be at least one skill file to mirror."""
        assert len(SOURCE_SKILL_FILES) > 0, "No source skill files found"

    @pytest.mark.parametrize("rel_path", SOURCE_SKILL_FILES)
    def test_mirror_file_exists(self, rel_path: str) -> None:
        """Each source skill file must have a corresponding mirror file."""
        mirror_path = MIRROR_SKILLS_DIR / rel_path
        assert mirror_path.exists(), (
            f"Mirror file missing: .claude/skills/{rel_path}\n"
            f"Source file exists at: src/lexibrary/templates/rules/skills/{rel_path}\n"
            f"Run: cp src/lexibrary/templates/rules/skills/{rel_path} "
            f".claude/skills/{rel_path}"
        )

    @pytest.mark.parametrize("rel_path", SOURCE_SKILL_FILES)
    def test_mirror_file_identical(self, rel_path: str) -> None:
        """Each mirror file must be byte-identical to its source."""
        source_path = SOURCE_SKILLS_DIR / rel_path
        mirror_path = MIRROR_SKILLS_DIR / rel_path
        if not mirror_path.exists():
            pytest.skip(f"Mirror file missing (covered by test_mirror_file_exists)")

        source_content = source_path.read_text(encoding="utf-8")
        mirror_content = mirror_path.read_text(encoding="utf-8")
        assert source_content == mirror_content, (
            f"Mirror file differs from source: .claude/skills/{rel_path}\n"
            f"Source: src/lexibrary/templates/rules/skills/{rel_path}\n"
            f"Copy the updated source to the mirror to fix."
        )
