"""Bottom-up directory traversal with ignore-pattern filtering."""

from __future__ import annotations

import os
from pathlib import Path

from lexibrary.ignore.matcher import IgnoreMatcher


def discover_directories_bottom_up(
    root: Path,
    ignore_matcher: IgnoreMatcher,
) -> list[Path]:
    """Discover all directories under root, sorted deepest-first.

    Uses os.walk with topdown=True to enable in-place pruning of ignored
    directories. Collects all directory paths, then sorts by depth
    (deepest first) so child .aindex files exist before parents are processed.

    Args:
        root: Project root directory.
        ignore_matcher: Matcher for filtering ignored directories.

    Returns:
        List of directory Paths, deepest first, root last.
    """
    directories: list[Path] = []

    for dirpath, dirnames, _filenames in os.walk(root, topdown=True):
        current = Path(dirpath)

        # Prune ignored directories in-place (modifies dirnames for os.walk)
        dirnames[:] = [d for d in dirnames if ignore_matcher.should_descend(current / d)]

        directories.append(current)

    # Sort by depth (deepest first); ties broken alphabetically
    directories.sort(key=lambda p: (-len(p.parts), str(p)))

    return directories


def list_directory_files(
    directory: Path,
    ignore_matcher: IgnoreMatcher,
    binary_extensions: set[str],
) -> tuple[list[Path], list[Path]]:
    """List files in a directory, separating indexable from skipped.

    Ignored files are excluded entirely. Files with known binary extensions
    are placed in the skipped list. Files that cannot be stat'd are skipped.

    Args:
        directory: Directory to list.
        ignore_matcher: Matcher for filtering ignored files.
        binary_extensions: Set of extensions (with leading dot) to skip.

    Returns:
        Tuple of (indexable_files, skipped_files).
    """
    indexable: list[Path] = []
    skipped: list[Path] = []

    try:
        entries = sorted(directory.iterdir())
    except PermissionError:
        return [], []

    for entry in entries:
        if not entry.is_file():
            continue

        if ignore_matcher.is_ignored(entry):
            continue

        if entry.suffix.lower() in binary_extensions:
            skipped.append(entry)
        else:
            indexable.append(entry)

    return indexable, skipped
