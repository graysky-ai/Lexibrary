"""Claude Code environment rule generation.

Generates:
- ``CLAUDE.md`` — marker-delimited Lexibrary section with core agent rules
- ``.claude/commands/lexi-orient.md`` — orient session-start command
- ``.claude/commands/lexi-search.md`` — cross-artifact search command

The ``CLAUDE.md`` file uses marker-based section management so that
user-authored content outside the markers is preserved across updates.
Command files are standalone and overwritten on each generation.
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


def generate_claude_rules(project_root: Path) -> list[Path]:
    """Generate Claude Code agent rule files at *project_root*.

    Creates or updates:

    1. ``CLAUDE.md`` — Lexibrary section appended (new file / no markers)
       or replaced (existing markers).
    2. ``.claude/commands/lexi-orient.md`` — orient skill command file.
    3. ``.claude/commands/lexi-search.md`` — search skill command file.

    Args:
        project_root: Absolute path to the project root directory.

    Returns:
        List of absolute paths to all created or updated files.
    """
    created: list[Path] = []

    # --- CLAUDE.md ---
    claude_md = project_root / "CLAUDE.md"
    core_rules = get_core_rules()

    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        if has_lexibrary_section(existing):
            updated = replace_lexibrary_section(existing, core_rules)
        else:
            updated = append_lexibrary_section(existing, core_rules)
    else:
        updated = append_lexibrary_section("", core_rules)

    claude_md.write_text(updated, encoding="utf-8")
    created.append(claude_md)

    # --- .claude/commands/ ---
    commands_dir = project_root / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    orient_file = commands_dir / "lexi-orient.md"
    orient_file.write_text(get_orient_skill_content(), encoding="utf-8")
    created.append(orient_file)

    search_file = commands_dir / "lexi-search.md"
    search_file.write_text(get_search_skill_content(), encoding="utf-8")
    created.append(search_file)

    return created
