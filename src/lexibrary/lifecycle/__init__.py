"""Lifecycle management for Lexibrary artifacts."""

from __future__ import annotations

from lexibrary.lifecycle.comments import append_comment, comment_count, read_comments
from lexibrary.lifecycle.concept_comments import (
    append_concept_comment,
    concept_comment_count,
    concept_comment_path,
    read_concept_comments,
)
from lexibrary.lifecycle.convention_comments import (
    append_convention_comment,
    convention_comment_count,
    convention_comment_path,
    read_convention_comments,
)
from lexibrary.lifecycle.design_comments import (
    append_design_comment,
    design_comment_count,
    design_comment_path,
    read_design_comments,
)
from lexibrary.lifecycle.models import ArtefactComment, ArtefactCommentFile
from lexibrary.lifecycle.stack_comments import (
    append_stack_comment,
    read_stack_comments,
    stack_comment_count,
    stack_comment_path,
)

__all__ = [
    "ArtefactComment",
    "ArtefactCommentFile",
    "append_comment",
    "append_concept_comment",
    "append_convention_comment",
    "append_design_comment",
    "append_stack_comment",
    "comment_count",
    "concept_comment_count",
    "concept_comment_path",
    "convention_comment_count",
    "convention_comment_path",
    "design_comment_count",
    "design_comment_path",
    "read_comments",
    "read_concept_comments",
    "read_convention_comments",
    "read_design_comments",
    "read_stack_comments",
    "stack_comment_count",
    "stack_comment_path",
]
