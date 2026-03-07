"""Shared Pydantic 2 models for artefact comment files.

All artefact types (design files, conventions, concepts) use sibling
``.comments.yaml`` files for feedback.  The models here provide the
common structure: a single comment with ``body`` + ``date``, and a
container that holds an ordered list of comments.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ArtefactComment(BaseModel):
    """A single comment recorded against an artefact.

    Comments are append-only entries stored in a sibling
    ``.comments.yaml`` file.  They carry only a free-form body and a
    UTC timestamp -- no agent attribution, confidence, or verification
    metadata.
    """

    body: str = Field(..., min_length=1)
    """Free-form comment text."""

    date: datetime
    """UTC timestamp when the comment was created."""


class ArtefactCommentFile(BaseModel):
    """Container model for a ``.comments.yaml`` file.

    The YAML structure is::

        comments:
          - body: "Some observation..."
            date: "2026-03-03T14:30:00"
          - body: "Another comment..."
            date: "2026-03-04T09:15:00"
    """

    comments: list[ArtefactComment] = Field(default_factory=list)
    """Ordered list of comments (oldest first)."""
