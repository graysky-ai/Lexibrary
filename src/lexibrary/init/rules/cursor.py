"""Cursor environment rule generation.

Generates:
- ``.cursor/rules/lexibrary.mdc`` — MDC rules file with YAML frontmatter
  (``alwaysApply: true``) containing the core Lexibrary agent rules.
- ``.cursor/rules/lexibrary-editing.mdc`` — MDC rules file scoped to source
  files (``alwaysApply: false``, glob-triggered) with editing instructions.
- ``.cursor/skills/lexi.md`` — combined skill content (orient, search,
  lookup, concepts, stack).

All files are standalone and overwritten on each generation (no marker-based
section management needed since Cursor scans dedicated directories).
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.init.rules.base import (
    get_concepts_skill_content,
    get_core_rules,
    get_lookup_skill_content,
    get_orient_skill_content,
    get_search_skill_content,
    get_stack_skill_content,
)
from lexibrary.templates import read_template

# Default scope root used when config is not available
_DEFAULT_SCOPE_ROOT = "src"


def generate_cursor_rules(
    project_root: Path,
    *,
    scope_root: str = _DEFAULT_SCOPE_ROOT,
) -> list[Path]:
    """Generate Cursor agent rule files at *project_root*.

    Creates or overwrites:

    1. ``.cursor/rules/lexibrary.mdc`` — MDC file with YAML frontmatter
       (``description``, ``globs``, ``alwaysApply: true``) followed by core
       agent rules.
    2. ``.cursor/rules/lexibrary-editing.mdc`` — MDC file scoped to source
       files under *scope_root* with editing instructions.
    3. ``.cursor/skills/lexi.md`` — combined skills (orient, search, lookup,
       concepts, stack).

    Args:
        project_root: Absolute path to the project root directory.
        scope_root: Source root directory for glob-scoped editing rules
            (default: ``"src"``).

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

    # --- .cursor/rules/lexibrary-editing.mdc ---
    editing_mdc_file = rules_dir / "lexibrary-editing.mdc"
    editing_content = _build_editing_mdc_content(scope_root)
    editing_mdc_file.write_text(editing_content, encoding="utf-8")
    created.append(editing_mdc_file)

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


def _build_editing_mdc_content(scope_root: str) -> str:
    """Build the editing-scoped ``.mdc`` file content.

    The editing rule uses ``alwaysApply: false`` and a glob pattern
    scoped to *scope_root* so it activates only when source files are
    being edited.

    Args:
        scope_root: Source root directory for glob patterns.

    Returns:
        Complete editing MDC file content as a string.
    """
    frontmatter = (
        "---\n"
        "description: Lexibrary editing rules — auto-lookup and design file reminders\n"
        f'globs: "{scope_root}/**"\n'
        "alwaysApply: false\n"
        "---"
    )
    body = read_template("cursor/editing-rules.md")
    return f"{frontmatter}\n{body}"


def _build_skills_content() -> str:
    """Build the combined skills file content.

    Returns:
        Combined orient, search, lookup, concepts, and stack skill content.
    """
    orient = get_orient_skill_content()
    search = get_search_skill_content()
    lookup = get_lookup_skill_content()
    concepts = get_concepts_skill_content()
    stack = get_stack_skill_content()
    return f"{orient}\n\n{search}\n\n{lookup}\n\n{concepts}\n\n{stack}\n"
