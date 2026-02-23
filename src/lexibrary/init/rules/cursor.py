"""Cursor environment rule generation.

Generates:
- ``.cursor/rules/lexibrary.mdc`` — MDC rules file with YAML frontmatter
  (``alwaysApply: true``) containing the core Lexibrary agent rules.
- ``.cursor/skills/lexi.md`` — combined orient and search skill content.

Both files are standalone and overwritten on each generation (no marker-based
section management needed since Cursor scans dedicated directories).
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.init.rules.base import (
    get_core_rules,
    get_orient_skill_content,
    get_search_skill_content,
)


def generate_cursor_rules(project_root: Path) -> list[Path]:
    """Generate Cursor agent rule files at *project_root*.

    Creates or overwrites:

    1. ``.cursor/rules/lexibrary.mdc`` — MDC file with YAML frontmatter
       (``description``, ``globs``, ``alwaysApply: true``) followed by core
       agent rules.
    2. ``.cursor/skills/lexi.md`` — combined orient and search skills.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        List of absolute paths to all created or updated files.
    """
    created: list[Path] = []

    # --- .cursor/rules/lexibrary.mdc ---
    rules_dir = project_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    mdc_file = rules_dir / "lexibrary.mdc"
    mdc_content = _build_mdc_content()
    mdc_file.write_text(mdc_content, encoding="utf-8")
    created.append(mdc_file)

    # --- .cursor/skills/lexi.md ---
    skills_dir = project_root / ".cursor" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    skills_file = skills_dir / "lexi.md"
    skills_content = _build_skills_content()
    skills_file.write_text(skills_content, encoding="utf-8")
    created.append(skills_file)

    return created


def _build_mdc_content() -> str:
    """Build the ``.mdc`` file content with YAML frontmatter and core rules.

    Returns:
        Complete MDC file content as a string.
    """
    frontmatter = (
        "---\n"
        "description: Lexibrary agent rules for codebase navigation\n"
        "globs:\n"
        "alwaysApply: true\n"
        "---"
    )
    return f"{frontmatter}\n{get_core_rules()}\n"


def _build_skills_content() -> str:
    """Build the combined skills file content.

    Returns:
        Combined orient and search skill content.
    """
    orient = get_orient_skill_content()
    search = get_search_skill_content()
    return f"{orient}\n\n{search}\n"
