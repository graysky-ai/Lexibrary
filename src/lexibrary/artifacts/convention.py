"""Pydantic 2 models for convention file artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from lexibrary.artifacts.slugs import slugify


class ConventionFileFrontmatter(BaseModel):
    """Validated YAML frontmatter for a convention file."""

    title: str
    scope: str = "project"
    tags: list[str] = []
    status: Literal["draft", "active", "deprecated"] = "draft"
    source: Literal["user", "agent", "config"] = "user"
    priority: int = 0
    aliases: list[str] = []
    deprecated_at: str | None = None


class ConventionFile(BaseModel):
    """Represents a convention file with validated frontmatter and freeform body."""

    frontmatter: ConventionFileFrontmatter
    body: str = ""
    rule: str = ""
    file_path: Path | None = None

    @property
    def name(self) -> str:
        """Return the convention display name from frontmatter."""
        return self.frontmatter.title

    @property
    def scope(self) -> str:
        """Return the convention scope from frontmatter."""
        return self.frontmatter.scope


# -- Slug / path helpers ----------------------------------------------------


def convention_slug(title: str) -> str:
    """Derive a filesystem-safe slug from a convention title.

    Delegates to :func:`lexibrary.artifacts.slugs.slugify`.
    """
    return slugify(title)


def convention_file_path(title: str, conventions_dir: Path) -> Path:
    """Return a unique file path for a convention in the given directory.

    Returns ``conventions_dir / "<slug>.md"``, appending a numeric suffix
    (``-2``, ``-3``, ...) if the path already exists on disk.
    """
    slug = convention_slug(title)
    path = conventions_dir / f"{slug}.md"
    if not path.exists():
        return path

    counter = 2
    while True:
        candidate = conventions_dir / f"{slug}-{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1
