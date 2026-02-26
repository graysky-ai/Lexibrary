"""Pydantic 2 models for convention file artifacts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class ConventionFileFrontmatter(BaseModel):
    """Validated YAML frontmatter for a convention file."""

    title: str
    scope: str = "project"
    tags: list[str] = []
    status: Literal["draft", "active", "deprecated"] = "draft"
    source: Literal["user", "agent", "config"] = "user"
    priority: int = 0


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

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_MULTI_HYPHEN_RE = re.compile(r"-{2,}")


def convention_slug(title: str) -> str:
    """Derive a filesystem-safe slug from a convention title.

    Steps:
    1. Lowercase the title
    2. Replace spaces and non-alphanumeric characters with hyphens
    3. Collapse consecutive hyphens
    4. Strip leading/trailing hyphens
    5. Truncate to 60 characters at a word boundary
    """
    slug = title.lower()
    slug = _NON_ALNUM_RE.sub("-", slug)
    slug = _MULTI_HYPHEN_RE.sub("-", slug)
    slug = slug.strip("-")

    if len(slug) <= 60:
        return slug

    # Truncate at a word boundary (hyphen boundary in slug)
    truncated = slug[:60]
    # Find last hyphen within the truncated portion
    last_hyphen = truncated.rfind("-")
    if last_hyphen > 0:
        truncated = truncated[:last_hyphen]
    return truncated.strip("-")


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
