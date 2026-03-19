"""Pydantic 2 models for playbook file artifacts."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from lexibrary.artifacts.slugs import slugify


class PlaybookFileFrontmatter(BaseModel):
    """Validated YAML frontmatter for a playbook file."""

    title: str = Field(
        ...,
        description="Semantic name; canonical identifier for slug, wikilinks, and lookups",
    )
    trigger_files: list[str] = []
    tags: list[str] = []
    status: Literal["draft", "active", "deprecated"] = "draft"
    source: Literal["user", "agent"] = "user"
    estimated_minutes: int | None = None
    last_verified: date | None = None
    deprecated_at: datetime | None = None
    superseded_by: str | None = None
    aliases: list[str] = []


class PlaybookFile(BaseModel):
    """Represents a playbook file with validated frontmatter and freeform body."""

    frontmatter: PlaybookFileFrontmatter
    body: str = ""
    overview: str = ""
    file_path: Path | None = None

    @property
    def name(self) -> str:
        """Return the playbook display name from frontmatter."""
        return self.frontmatter.title


# -- Slug / path helpers ----------------------------------------------------


def playbook_slug(title: str) -> str:
    """Derive a filesystem-safe slug from a playbook title.

    Delegates to :func:`lexibrary.artifacts.slugs.slugify`.
    """
    return slugify(title)


def playbook_file_path(title: str, playbooks_dir: Path) -> Path:
    """Return a unique file path for a playbook in the given directory.

    Returns ``playbooks_dir / "<slug>.md"``, appending a numeric suffix
    (``-2``, ``-3``, ...) if the path already exists on disk.
    """
    slug = playbook_slug(title)
    path = playbooks_dir / f"{slug}.md"
    if not path.exists():
        return path

    counter = 2
    while True:
        candidate = playbooks_dir / f"{slug}-{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1
