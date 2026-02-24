"""Template-based design file scaffold generator (no LLM required)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def generate_design_scaffold(source_path: Path, project_root: Path) -> str:
    """Create a template design file scaffold without LLM calls.

    Produces a markdown string with YAML frontmatter and placeholder
    sections matching the standard design file format.

    Args:
        source_path: Absolute or project-relative path to the source file.
        project_root: Absolute path to the project root.

    Returns:
        A markdown string containing the scaffold content ready to be
        written to the mirror path.
    """
    # Compute relative path from project root
    if source_path.is_absolute():
        rel_path = str(source_path.relative_to(project_root))
    else:
        rel_path = str(source_path)

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    filename = Path(rel_path).name

    return f"""---
source_path: {rel_path}
updated_by: agent
date: {today}
---

# {filename}

<!-- TODO: Describe the purpose of this module -->

## Purpose

<!-- What does this module do? What problem does it solve? -->

## Key Components

<!-- List the main classes, functions, or interfaces -->

## Dependencies

<!-- What does this module depend on? What depends on it? -->
"""
