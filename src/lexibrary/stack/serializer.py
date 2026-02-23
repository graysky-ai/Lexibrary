"""Serializer for Stack post artifacts to markdown format."""

from __future__ import annotations

import yaml

from lexibrary.stack.models import StackPost


def serialize_stack_post(post: StackPost) -> str:
    """Serialize a StackPost to a markdown string with YAML frontmatter.

    Produces:
    - ``---`` delimited YAML frontmatter containing all StackPostFrontmatter fields
    - ``## Problem`` section with the problem description
    - ``### Evidence`` section with evidence items as a bullet list
    - ``## Answers`` section containing answer blocks (if any)
    - Each answer as ``### A{n}`` with metadata line, body, and ``#### Comments``
    - Trailing newline
    """
    parts: list[str] = []

    # --- YAML frontmatter ---
    parts.append(_serialize_frontmatter(post))

    # --- ## Problem ---
    parts.append("## Problem\n\n")
    parts.append(post.problem.rstrip("\n"))
    parts.append("\n\n")

    # --- ### Evidence ---
    parts.append("### Evidence\n\n")
    if post.evidence:
        for item in post.evidence:
            parts.append(f"- {item}\n")
    parts.append("\n")

    # --- ## Answers ---
    if post.answers:
        parts.append("## Answers\n\n")
        for answer in post.answers:
            parts.append(f"### A{answer.number}\n\n")

            # Metadata line
            meta = (
                f"**Date:** {answer.date.isoformat()}"
                f" | **Author:** {answer.author}"
                f" | **Votes:** {answer.votes}"
            )
            if answer.accepted:
                meta += " | **Accepted:** true"
            parts.append(meta + "\n\n")

            # Body
            parts.append(answer.body.rstrip("\n"))
            parts.append("\n\n")

            # Comments
            parts.append("#### Comments\n\n")
            if answer.comments:
                for comment in answer.comments:
                    parts.append(f"{comment}\n")
                parts.append("\n")

    result = "".join(parts)
    # Ensure trailing newline
    if not result.endswith("\n"):
        result += "\n"
    return result


def _serialize_frontmatter(post: StackPost) -> str:
    """Serialize the StackPostFrontmatter to YAML frontmatter block."""
    fm = post.frontmatter
    fm_data: dict[str, object] = {
        "id": fm.id,
        "title": fm.title,
        "tags": fm.tags,
        "status": fm.status,
        "created": fm.created.isoformat(),
        "author": fm.author,
        "bead": fm.bead,
        "votes": fm.votes,
        "duplicate_of": fm.duplicate_of,
        "refs": {
            "concepts": fm.refs.concepts,
            "files": fm.refs.files,
            "designs": fm.refs.designs,
        },
    }

    fm_str = yaml.dump(
        fm_data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    ).rstrip("\n")

    return f"---\n{fm_str}\n---\n\n"
