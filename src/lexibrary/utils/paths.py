"""Path construction utilities for the .lexibrary/ output tree."""

from __future__ import annotations

from pathlib import Path

LEXIBRARY_DIR = ".lexibrary"


def mirror_path(project_root: Path, source_file: Path) -> Path:
    """Compute the design-file mirror path for a source file.

    Maps ``src/auth/login.py`` → ``.lexibrary/src/auth/login.py.md``.

    Args:
        project_root: Absolute path to the project root.
        source_file: Absolute or project-relative path to a source file.

    Returns:
        Absolute path to the mirrored design file inside ``.lexibrary/``.
    """
    relative = source_file.relative_to(project_root) if source_file.is_absolute() else source_file
    return project_root / LEXIBRARY_DIR / f"{relative}.md"


def aindex_path(project_root: Path, directory: Path) -> Path:
    """Compute the ``.aindex`` path for a directory.

    Maps ``src/auth/`` → ``.lexibrary/src/auth/.aindex``.

    Args:
        project_root: Absolute path to the project root.
        directory: Absolute or project-relative path to a directory.

    Returns:
        Absolute path to the ``.aindex`` file inside ``.lexibrary/``.
    """
    relative = directory.relative_to(project_root) if directory.is_absolute() else directory
    return project_root / LEXIBRARY_DIR / relative / ".aindex"


def iwh_path(project_root: Path, source_directory: Path) -> Path:
    """Compute the ``.iwh`` file path for a source directory.

    Maps ``src/auth/`` -> ``.lexibrary/src/auth/.iwh``.

    Args:
        project_root: Absolute path to the project root.
        source_directory: Absolute or project-relative path to a source
            directory.

    Returns:
        Absolute path to the ``.iwh`` file inside ``.lexibrary/``.
    """
    relative = (
        source_directory.relative_to(project_root)
        if source_directory.is_absolute()
        else source_directory
    )
    return project_root / LEXIBRARY_DIR / relative / ".iwh"
