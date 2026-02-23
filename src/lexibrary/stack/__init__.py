"""Stack module — Stack Overflow-style Q&A knowledge base for Lexibrary."""

from __future__ import annotations

from lexibrary.stack.index import StackIndex
from lexibrary.stack.models import (
    StackAnswer,
    StackPost,
    StackPostFrontmatter,
    StackPostRefs,
)
from lexibrary.stack.mutations import (
    accept_answer,
    add_answer,
    mark_duplicate,
    mark_outdated,
    record_vote,
)
from lexibrary.stack.parser import parse_stack_post
from lexibrary.stack.serializer import serialize_stack_post
from lexibrary.stack.template import render_post_template

__all__ = [
    "StackAnswer",
    "StackIndex",
    "StackPost",
    "StackPostFrontmatter",
    "StackPostRefs",
    "accept_answer",
    "add_answer",
    "mark_duplicate",
    "mark_outdated",
    "parse_stack_post",
    "record_vote",
    "render_post_template",
    "serialize_stack_post",
]
