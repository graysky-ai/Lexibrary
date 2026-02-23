"""Pydantic 2 models for concept file artifacts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ConceptFileFrontmatter(BaseModel):
    """Validated YAML frontmatter for a concept file."""

    title: str
    aliases: list[str] = []
    tags: list[str] = []
    status: Literal["draft", "active", "deprecated"] = "draft"
    superseded_by: str | None = None


class ConceptFile(BaseModel):
    """Represents a concept file with validated frontmatter and freeform body."""

    frontmatter: ConceptFileFrontmatter
    body: str = ""
    summary: str = ""
    related_concepts: list[str] = []
    linked_files: list[str] = []
    decision_log: list[str] = []

    @property
    def name(self) -> str:
        """Return the concept display name from frontmatter."""
        return self.frontmatter.title
