"""Git conflict marker detection utility."""

from __future__ import annotations

from pathlib import Path

# The seven-character conflict marker that Git places at the start of a line.
_CONFLICT_PREFIX = "<<<<<<<"


def has_conflict_markers(source_path: Path) -> bool:
    """Check whether a file contains git merge conflict markers.

    Only markers that appear at the very start of a line (``<<<<<<<``)
    are considered.  Files that do not exist or contain binary content
    are handled gracefully.

    Args:
        source_path: Path to the file to check.

    Returns:
        ``True`` if at least one line starts with ``<<<<<<<``,
        ``False`` otherwise (including non-existent files).
    """
    try:
        with open(source_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith(_CONFLICT_PREFIX):
                    return True
    except (OSError, FileNotFoundError):
        return False

    return False
