"""Describe service — billboard update logic extracted from CLI handler."""

from __future__ import annotations

from pathlib import Path

from lexibrary.artifacts.aindex_parser import parse_aindex
from lexibrary.artifacts.aindex_serializer import serialize_aindex
from lexibrary.exceptions import LexibraryError
from lexibrary.utils.paths import aindex_path


class DescribeError(LexibraryError):
    """Error raised when a billboard update fails."""


def update_billboard(project_root: Path, directory: Path, description: str) -> Path:
    """Update the billboard description in a directory's .aindex file.

    Args:
        project_root: Absolute path to the project root (must contain .lexibrary/).
        directory: Absolute path to the target directory whose billboard to update.
        description: New billboard description string.

    Returns:
        Path to the updated .aindex file.

    Raises:
        DescribeError: If the directory does not exist, is not a directory,
            is outside the project root, or has no parseable .aindex file.
    """
    target = Path(directory).resolve()
    root = Path(project_root).resolve()

    if not target.exists():
        msg = f"Directory not found: {directory}"
        raise DescribeError(msg)

    if not target.is_dir():
        msg = f"Not a directory: {directory}"
        raise DescribeError(msg)

    # Ensure directory is within the project root
    try:
        target.relative_to(root)
    except ValueError:
        msg = f"Directory {directory} is outside project root {project_root}"
        raise DescribeError(msg) from None

    aindex_file = aindex_path(root, target)

    if not aindex_file.exists():
        msg = (
            f"No .aindex file found for {directory}."
            f" Run `lexictl index {directory}` to generate one first."
        )
        raise DescribeError(msg)

    aindex = parse_aindex(aindex_file)
    if aindex is None:
        msg = f"Failed to parse .aindex file: {aindex_file}"
        raise DescribeError(msg)

    aindex.billboard = description
    serialized = serialize_aindex(aindex)
    aindex_file.write_text(serialized, encoding="utf-8")

    return aindex_file
