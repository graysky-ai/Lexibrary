"""Shared skeleton design file generation.

Extracts the core skeleton generation logic from ``bootstrap.py`` into a
reusable helper that both ``bootstrap_quick`` and the size-gate / truncation
fallback paths can call.
"""

from __future__ import annotations

import ast
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from lexibrary.archivist.dependency_extractor import extract_dependencies
from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.ast_parser import compute_hashes, parse_interface, render_skeleton

UpdatedByLiteral = Literal[
    "archivist", "agent", "bootstrap-quick", "skeleton-fallback", "maintainer"
]

logger = logging.getLogger(__name__)

_GENERATOR_ID = "lexibrary-v2"


def _extract_module_docstring(source_path: Path) -> str | None:
    """Extract the module-level docstring from a Python file.

    Returns the docstring text or None if no module docstring is found.
    """
    if source_path.suffix not in (".py", ".pyi"):
        return None

    try:
        source = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    return ast.get_docstring(tree)


def heuristic_description(source_path: Path) -> str:
    """Generate a heuristic description from filename and docstrings.

    Checks for a module-level docstring first. Falls back to a
    description derived from the filename.
    """
    docstring = _extract_module_docstring(source_path)
    if docstring:
        # Use first line of docstring as description
        first_line = docstring.strip().split("\n")[0].strip()
        if first_line:
            return first_line

    # Fallback: generate from filename
    stem = source_path.stem
    if stem == "__init__":
        return f"Package initializer for {source_path.parent.name}"
    if stem == "__main__":
        return f"Entry point for {source_path.parent.name}"

    # Convert snake_case to readable
    readable = stem.replace("_", " ").strip()
    return f"Design file for {readable}"


def generate_skeleton_design(
    source_path: Path,
    project_root: Path,
    *,
    updated_by: UpdatedByLiteral = "skeleton-fallback",
    summary_suffix: str = "",
) -> DesignFile:
    """Generate a skeleton design file for a single source file without LLM.

    Uses tree-sitter for interface extraction, AST for dependency extraction,
    and heuristics for the description. Returns a ``DesignFile`` model that the
    caller can serialize and write.

    Args:
        source_path: Absolute path to the source file.
        project_root: Absolute path to the project root.
        updated_by: Value for ``DesignFileFrontmatter.updated_by``.
        summary_suffix: Optional text appended to the summary (e.g. token
            count guidance for size-gated files).

    Returns:
        A fully-populated ``DesignFile`` model ready for serialization.
    """
    # Compute hashes
    content_hash, interface_hash = compute_hashes(source_path)

    rel_path = str(source_path.relative_to(project_root))

    # Extract interface skeleton
    skeleton = parse_interface(source_path)
    skeleton_text = ""
    if skeleton is not None:
        skeleton_text = render_skeleton(skeleton)

    # Extract dependencies
    deps = extract_dependencies(source_path, project_root)

    # Heuristic description
    description = heuristic_description(source_path)

    # Build summary (description + optional suffix)
    summary = description + summary_suffix

    # Build DesignFile model
    return DesignFile(
        source_path=rel_path,
        frontmatter=DesignFileFrontmatter(
            description=description,
            updated_by=updated_by,
        ),
        summary=summary,
        interface_contract=skeleton_text,
        dependencies=deps,
        dependents=[],
        metadata=StalenessMetadata(
            source=rel_path,
            source_hash=content_hash,
            interface_hash=interface_hash,
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator=_GENERATOR_ID,
        ),
    )
