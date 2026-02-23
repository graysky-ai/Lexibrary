"""Project root resolution by walking upward for .lexibrary/ directory."""

from __future__ import annotations

from pathlib import Path

from lexibrary.exceptions import LexibraryNotFoundError


def find_project_root(start: Path | None = None) -> Path:
    """Find project root by walking upward looking for a .lexibrary/ directory.

    Args:
        start: Directory to start search from. Defaults to current working directory.

    Returns:
        Path to the project root directory (the parent of .lexibrary/).

    Raises:
        LexibraryNotFoundError: If no .lexibrary/ directory is found.
    """
    current = Path.cwd() if start is None else Path(start).resolve()

    while True:
        if (current / ".lexibrary").is_dir():
            return current

        if current.parent == current:
            break

        current = current.parent

    origin = Path.cwd() if start is None else Path(start).resolve()
    msg = f"No .lexibrary/ directory found walking up from {origin}"
    raise LexibraryNotFoundError(msg)
