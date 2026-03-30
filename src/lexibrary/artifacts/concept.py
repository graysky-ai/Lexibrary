"""Pydantic 2 models for concept file artifacts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from lexibrary.artifacts.slugs import slugify


class ConceptFileFrontmatter(BaseModel):
    """Validated YAML frontmatter for a concept file."""

    title: str
    id: str
    aliases: list[str] = []
    tags: list[str] = []
    status: Literal["draft", "active", "deprecated"] = "active"
    superseded_by: str | None = None
    deprecated_at: datetime | None = None


class ConceptFile(BaseModel):
    """Represents a concept file with validated frontmatter and freeform body."""

    frontmatter: ConceptFileFrontmatter
    body: str = ""
    summary: str = ""
    related_concepts: list[str] = []
    linked_files: list[str] = []
    decision_log: list[str] = []
    file_path: Path | None = None

    @property
    def name(self) -> str:
        """Return the concept display name from frontmatter."""
        return self.frontmatter.title


# -- Slug / path helpers ----------------------------------------------------


def concept_slug(title: str) -> str:
    """Derive a filesystem-safe slug from a concept title.

    Delegates to :func:`lexibrary.artifacts.slugs.slugify`.
    """
    return slugify(title)


def concept_file_path(concept_id: str, title: str, concepts_dir: Path) -> Path:
    """Return the file path for a concept with an ID-prefixed filename.

    Returns ``concepts_dir / "<concept_id>-<slug>.md"`` (e.g.
    ``CN-001-error-handling.md``).  No collision suffix is needed because
    IDs are unique by construction.
    """
    slug = concept_slug(title)
    return concepts_dir / f"{concept_id}-{slug}.md"
