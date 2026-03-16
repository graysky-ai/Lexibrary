"""Pydantic 2 models for Stack posts — the issue knowledge base."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

StackStatus = Literal["open", "resolved", "outdated", "duplicate", "stale"]
ResolutionType = Literal["fix", "workaround", "wontfix", "cannot_reproduce", "by_design"]


class StackPostRefs(BaseModel):
    """Cross-references from a Stack post to other artifacts."""

    concepts: list[str] = []
    files: list[str] = []
    designs: list[str] = []


class StackPostFrontmatter(BaseModel):
    """Validated YAML frontmatter for a Stack post."""

    id: str
    title: str
    tags: list[str] = Field(..., min_length=1)
    status: StackStatus = "open"
    created: date
    author: str
    bead: str | None = None
    votes: int = 0
    duplicate_of: str | None = None
    refs: StackPostRefs = Field(default_factory=StackPostRefs)
    resolution_type: ResolutionType | None = None
    stale_at: datetime | None = None
    last_vote_at: datetime | None = None


class StackFinding(BaseModel):
    """A single finding within a Stack post."""

    number: int
    date: date
    author: str
    votes: int = 0
    accepted: bool = False
    body: str
    comments: list[str] = []


class StackPost(BaseModel):
    """Represents a full Stack post with frontmatter, body sections, and findings."""

    frontmatter: StackPostFrontmatter
    problem: str
    context: str = ""
    evidence: list[str] = []
    attempts: list[str] = []
    findings: list[StackFinding] = []
    raw_body: str = ""
