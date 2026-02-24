"""Generic environment rule generation.

Generates:
- ``LEXIBRARY_RULES.md`` — a standalone file at the project root containing
  core agent rules with embedded orient and search skill content.

For environments without first-class Lexibrary integration (i.e. not Claude
Code, Cursor, or Codex), agents can be pointed to this single file.  The
file is fully overwritten on each generation — no marker management is needed
because the entire file is Lexibrary-owned.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.init.rules.base import (
    get_core_rules,
    get_orient_skill_content,
    get_search_skill_content,
)


def generate_generic_rules(project_root: Path) -> list[Path]:
    """Generate generic agent rule files at *project_root*.

    Creates or overwrites:

    1. ``LEXIBRARY_RULES.md`` — core rules plus embedded orient and search
       skill content.  Suitable for any AI coding agent.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        List of absolute paths to all created or updated files.
    """
    created: list[Path] = []

    rules_md = project_root / "LEXIBRARY_RULES.md"
    content = _build_content()
    rules_md.write_text(content, encoding="utf-8")
    created.append(rules_md)

    return created


def _build_content() -> str:
    """Build the full content for LEXIBRARY_RULES.md.

    Combines core rules with orient and search skill content into a
    single document.

    Returns:
        Combined rules and skills content.
    """
    core = get_core_rules()
    orient = get_orient_skill_content()
    search = get_search_skill_content()
    return f"{core}\n\n{orient}\n\n{search}\n"
