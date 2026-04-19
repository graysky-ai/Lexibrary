"""Pydantic 2 models for convention file artifacts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from lexibrary.artifacts.slugs import slugify


class ConventionFileFrontmatter(BaseModel):
    """Validated YAML frontmatter for a convention file."""

    title: str
    id: str
    scope: str = "project"
    tags: list[str] = []
    status: Literal["draft", "active", "deprecated"] = "draft"
    source: Literal["user", "agent", "config"] = "user"
    priority: int = 0
    aliases: list[str] = []
    deprecated_at: datetime | None = None
    deprecated_reason: str | None = Field(
        default=None,
        description=(
            "Free-text reason for deprecation. Set by lifecycle helpers and CLI "
            "deprecation commands."
        ),
    )


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

    @property
    def scope_paths(self) -> list[str]:
        """Return individual scope paths, splitting comma-separated values."""
        return split_scope(self.frontmatter.scope)


def split_scope(scope: str) -> list[str]:
    """Split a scope string into individual directory paths.

    Supports comma-separated multi-path scopes (e.g.
    ``"src/lexibrary/cli/, src/lexibrary/services/"``).  Returns
    ``["project"]`` unchanged.  Each path is stripped of surrounding
    whitespace and trailing slashes.
    """
    if scope == "project":
        return ["project"]
    return [part.strip().rstrip("/") for part in scope.split(",") if part.strip()]


# -- Slug / path helpers ----------------------------------------------------


def convention_slug(title: str) -> str:
    """Derive a filesystem-safe slug from a convention title.

    Delegates to :func:`lexibrary.artifacts.slugs.slugify`.
    """
    return slugify(title)


def convention_file_path(convention_id: str, title: str, conventions_dir: Path) -> Path:
    """Return the file path for a convention with an ID-prefixed filename.

    Returns ``conventions_dir / "<convention_id>-<slug>.md"`` (e.g.
    ``CV-001-use-utc-everywhere.md``).  No collision suffix is needed
    because IDs are unique by construction.
    """
    slug = convention_slug(title)
    return conventions_dir / f"{convention_id}-{slug}.md"
