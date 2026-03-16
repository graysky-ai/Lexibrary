"""Serializer for Stack post artifacts to markdown format."""

from __future__ import annotations

import yaml

from lexibrary.stack.models import StackPost


def serialize_stack_post(post: StackPost) -> str:
    """Serialize a StackPost to a markdown string with YAML frontmatter.

    Produces:
    - ``---`` delimited YAML frontmatter containing all StackPostFrontmatter fields
      (``resolution_type`` included only when not None)
    - ``## Problem`` section with the problem description
    - ``### Context`` section (conditional — only when non-empty)
    - ``### Evidence`` section with evidence items as a bullet list (conditional)
    - ``### Attempts`` section with attempt items as a bullet list (conditional)
    - ``## Findings`` section containing finding blocks (if any)
    - Each finding as ``### F{n}`` with metadata line, body, and ``#### Comments``
    - Trailing newline
    """
    parts: list[str] = []

    # --- YAML frontmatter ---
    parts.append(_serialize_frontmatter(post))

    # --- ## Problem ---
    parts.append("## Problem\n\n")
    parts.append(post.problem.rstrip("\n"))
    parts.append("\n\n")

    # --- ### Context (conditional) ---
    if post.context:
        parts.append("### Context\n\n")
        parts.append(post.context.rstrip("\n"))
        parts.append("\n\n")

    # --- ### Evidence (conditional) ---
    if post.evidence:
        parts.append("### Evidence\n\n")
        for item in post.evidence:
            parts.append(f"- {item}\n")
        parts.append("\n")

    # --- ### Attempts (conditional) ---
    if post.attempts:
        parts.append("### Attempts\n\n")
        for item in post.attempts:
            parts.append(f"- {item}\n")
        parts.append("\n")

    # --- ## Findings ---
    if post.findings:
        parts.append("## Findings\n\n")
        for finding in post.findings:
            parts.append(f"### F{finding.number}\n\n")

            # Metadata line
            meta = (
                f"**Date:** {finding.date.isoformat()}"
                f" | **Author:** {finding.author}"
                f" | **Votes:** {finding.votes}"
            )
            if finding.accepted:
                meta += " | **Accepted:** true"
            parts.append(meta + "\n\n")

            # Body
            parts.append(finding.body.rstrip("\n"))
            parts.append("\n\n")

            # Comments
            parts.append("#### Comments\n\n")
            if finding.comments:
                for comment in finding.comments:
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

    if fm.resolution_type is not None:
        fm_data["resolution_type"] = fm.resolution_type

    if fm.stale_at is not None:
        fm_data["stale_at"] = fm.stale_at.isoformat()

    if fm.last_vote_at is not None:
        fm_data["last_vote_at"] = fm.last_vote_at.isoformat()

    fm_str = yaml.dump(
        fm_data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    ).rstrip("\n")

    return f"---\n{fm_str}\n---\n\n"
