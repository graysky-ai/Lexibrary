"""Stack module — issue knowledge base for Lexibrary."""

from __future__ import annotations

from lexibrary.stack.helpers import find_post_path, stack_dir
from lexibrary.stack.index import StackIndex
from lexibrary.stack.models import (
    ResolutionType,
    StackFinding,
    StackPost,
    StackPostFrontmatter,
    StackPostRefs,
    StackStatus,
)
from lexibrary.stack.mutations import (
    accept_finding,
    add_finding,
    mark_duplicate,
    mark_outdated,
    mark_stale,
    mark_unstale,
    record_vote,
)
from lexibrary.stack.parser import parse_stack_post
from lexibrary.stack.serializer import serialize_stack_post
from lexibrary.stack.template import render_post_template

__all__ = [
    "ResolutionType",
    "StackFinding",
    "StackIndex",
    "StackPost",
    "StackPostFrontmatter",
    "StackPostRefs",
    "StackStatus",
    "accept_finding",
    "add_finding",
    "find_post_path",
    "mark_duplicate",
    "mark_outdated",
    "mark_stale",
    "mark_unstale",
    "parse_stack_post",
    "record_vote",
    "render_post_template",
    "serialize_stack_post",
    "stack_dir",
]
