"""Pydantic 2 models for Stack posts — the Q&A knowledge base."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

StackStatus = Literal["open", "resolved", "outdated", "duplicate"]


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


class StackAnswer(BaseModel):
    """A single answer within a Stack post."""

    number: int
    date: date
    author: str
    votes: int = 0
    accepted: bool = False
    body: str
    comments: list[str] = []


class StackPost(BaseModel):
    """Represents a full Stack post with frontmatter, problem, evidence, and answers."""

    frontmatter: StackPostFrontmatter
    problem: str
    evidence: list[str] = []
    answers: list[StackAnswer] = []
    raw_body: str = ""
