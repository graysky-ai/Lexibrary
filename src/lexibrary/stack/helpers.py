"""Stack helpers — domain utilities for stack filename conventions."""

from __future__ import annotations

from pathlib import Path


def stack_dir(project_root: Path) -> Path:
    """Return the .lexibrary/stack/ directory, creating it if needed."""
    d = project_root / ".lexibrary" / "stack"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_post_path(project_root: Path, post_id: str) -> Path | None:
    """Find the file path for a post ID (e.g. 'ST-001')."""
    sdir = project_root / ".lexibrary" / "stack"
    if not sdir.is_dir():
        return None
    for f in sdir.glob(f"{post_id}-*.md"):
        return f
    return None
