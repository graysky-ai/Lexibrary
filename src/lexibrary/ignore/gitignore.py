"""Gitignore file discovery and parsing."""

from __future__ import annotations

from pathlib import Path

import pathspec


def load_gitignore_specs(
    root: Path,
) -> list[tuple[Path, pathspec.PathSpec]]:
    """
    Find and parse all .gitignore files in a project tree.

    Args:
        root: Project root directory to search.

    Returns:
        List of (directory, PathSpec) tuples sorted by depth (root first).
        Each tuple contains the directory containing the .gitignore and its
        parsed PathSpec.
    """
    gitignore_files: list[tuple[Path, pathspec.PathSpec]] = []

    # Find all .gitignore files recursively
    for gitignore_path in root.rglob(".gitignore"):
        # Read and parse patterns
        try:
            with open(gitignore_path, encoding="utf-8") as f:
                patterns = f.read().splitlines()

            # Parse with gitignore pattern style
            spec = pathspec.PathSpec.from_lines("gitignore", patterns)
            gitignore_files.append((gitignore_path.parent, spec))
        except (OSError, UnicodeDecodeError):
            # Skip files that can't be read
            continue

    # Sort by directory depth (root first) for hierarchical matching
    gitignore_files.sort(key=lambda x: len(x[0].parts))

    return gitignore_files
