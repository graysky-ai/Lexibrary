"""Serializer for convention file artifacts to markdown format."""

from __future__ import annotations

import yaml

from lexibrary.artifacts.convention import ConventionFile


def serialize_convention_file(convention: ConventionFile) -> str:
    """Serialize a ConventionFile to a markdown string with YAML frontmatter.

    Produces:
    - ``---`` delimited YAML frontmatter (title, scope, tags, status,
      source, priority)
    - A blank line after the closing ``---``
    - The full body text
    - Trailing newline
    """
    fm_data: dict[str, object] = {
        "title": convention.frontmatter.title,
        "scope": convention.frontmatter.scope,
        "tags": convention.frontmatter.tags,
        "status": convention.frontmatter.status,
        "source": convention.frontmatter.source,
        "priority": convention.frontmatter.priority,
    }

    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    parts = [f"---\n{fm_str}\n---\n"]
    if convention.body:
        parts.append(convention.body)
    result = "".join(parts)
    if not result.endswith("\n"):
        result += "\n"
    return result
