"""Codex (OpenAI) environment rule generation.

Generates:
- ``AGENTS.md`` — marker-delimited Lexibrary section containing core agent
  rules with embedded orient and search skill content.

Codex reads ``AGENTS.md`` from the project root.  Unlike Claude Code which
uses separate command files, Codex receives all instructions in a single
file.  The marker-based approach preserves user-authored content outside
the Lexibrary section.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.init.rules.base import (
    get_core_rules,
    get_orient_skill_content,
    get_search_skill_content,
)
from lexibrary.init.rules.markers import (
    append_lexibrary_section,
    has_lexibrary_section,
    replace_lexibrary_section,
)


def generate_codex_rules(project_root: Path) -> list[Path]:
    """Generate Codex agent rule files at *project_root*.

    Creates or updates:

    1. ``AGENTS.md`` — Lexibrary section appended (new file / no markers)
       or replaced (existing markers).  Includes core rules plus embedded
       orient and search skill content.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        List of absolute paths to all created or updated files.
    """
    created: list[Path] = []

    agents_md = project_root / "AGENTS.md"
    section_content = _build_section_content()

    if agents_md.exists():
        existing = agents_md.read_text(encoding="utf-8")
        if has_lexibrary_section(existing):
            updated = replace_lexibrary_section(existing, section_content)
        else:
            updated = append_lexibrary_section(existing, section_content)
    else:
        updated = append_lexibrary_section("", section_content)

    agents_md.write_text(updated, encoding="utf-8")
    created.append(agents_md)

    return created


def _build_section_content() -> str:
    """Build the combined section content for AGENTS.md.

    Combines core rules with orient and search skill content into a
    single block that goes between the Lexibrary markers.

    Returns:
        Combined rules and skills content.
    """
    core = get_core_rules()
    orient = get_orient_skill_content()
    search = get_search_skill_content()
    return f"{core}\n\n{orient}\n\n{search}"
