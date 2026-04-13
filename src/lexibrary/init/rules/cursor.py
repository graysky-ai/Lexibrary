"""Cursor environment rule generation.

Generates:
- ``.cursor/rules/lexibrary.mdc`` — MDC rules file with YAML frontmatter
  (``alwaysApply: true``) containing the core Lexibrary agent rules.
- ``.cursor/rules/lexibrary-editing.mdc`` — MDC rules file scoped to source
  files (``alwaysApply: false``, glob-triggered) with editing instructions.
- ``.cursor/skills/lexi.md`` — combined skill content (search, lookup,
  concepts, stack).

All files are standalone and overwritten on each generation (no marker-based
section management needed since Cursor scans dedicated directories).
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.init.rules.base import (
    get_concepts_skill_content,
    get_core_rules,
    get_lookup_skill_content,
    get_search_skill_content,
    get_stack_skill_content,
)
from lexibrary.templates import read_template

# Default scope roots used when config is not available
_DEFAULT_SCOPE_ROOTS: list[str] = ["src"]


def generate_cursor_rules(
    project_root: Path,
    *,
    scope_roots: list[str] | None = None,
) -> list[Path]:
    """Generate Cursor agent rule files at *project_root*.

    Creates or overwrites:

    1. ``.cursor/rules/lexibrary.mdc`` — MDC file with YAML frontmatter
       (``description``, ``globs``, ``alwaysApply: true``) followed by core
       agent rules.
    2. ``.cursor/rules/lexibrary-editing.mdc`` — MDC file scoped to source
       files under *scope_roots* with editing instructions.
    3. ``.cursor/skills/lexi.md`` — combined skills (search, lookup,
       concepts, stack).

    Args:
        project_root: Absolute path to the project root directory.
        scope_roots: Source root directories for glob-scoped editing rules
            (default: ``["src"]``). Callers typically derive this from
            ``WizardAnswers.scope_roots`` via
            ``[sr.path for sr in answers.scope_roots]``. A single-element
            list emits a scalar ``globs:`` value; a multi-element list
            emits a YAML flow-style list (Block E of the ``multi-root``
            change).

    Returns:
        List of absolute paths to all created or updated files.
    """
    roots = list(scope_roots) if scope_roots else list(_DEFAULT_SCOPE_ROOTS)

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
    editing_content = _build_editing_mdc_content(roots)
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


def _build_editing_mdc_content(scope_roots: list[str]) -> str:
    """Build the editing-scoped ``.mdc`` file content.

    The editing rule uses ``alwaysApply: false`` and glob patterns
    scoped to *scope_roots* so it activates only when source files are
    being edited.

    Follows Block E of the ``multi-root`` change for the ``globs:`` line:

    * Single root → YAML scalar, e.g. ``globs: "src/**"``.
    * Multi-root → YAML flow-style list,
      e.g. ``globs: ["src/**", "baml_src/**"]``.

    Both forms are valid MDC/YAML; keeping a scalar in the single-root case
    minimises the diff for existing single-root installs.

    Args:
        scope_roots: Source root directories for glob patterns.

    Returns:
        Complete editing MDC file content as a string.
    """
    if len(scope_roots) == 1:
        globs_line = f'globs: "{scope_roots[0]}/**"'
    else:
        formatted = ", ".join(f'"{root}/**"' for root in scope_roots)
        globs_line = f"globs: [{formatted}]"

    frontmatter = (
        "---\n"
        "description: Lexibrary editing rules — auto-lookup and design file reminders\n"
        f"{globs_line}\n"
        "alwaysApply: false\n"
        "---"
    )
    body = read_template("cursor/editing-rules.md")
    return f"{frontmatter}\n{body}"


def _build_skills_content() -> str:
    """Build the combined skills file content.

    Returns:
        Combined search, lookup, concepts, and stack skill content.
    """
    search = get_search_skill_content()
    lookup = get_lookup_skill_content()
    concepts = get_concepts_skill_content()
    stack = get_stack_skill_content()
    return f"{search}\n\n{lookup}\n\n{concepts}\n\n{stack}\n"
